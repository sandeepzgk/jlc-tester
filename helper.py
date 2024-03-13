import os
import subprocess
import shutil
import argparse
import re

import logging

# Create necessary directories
def create_directories(lib_dir, temp_dir):
    os.makedirs(lib_dir, exist_ok=True)
    logging.info(f"Created directory: {lib_dir}")
    os.makedirs(temp_dir, exist_ok=True)
    logging.info(f"Created directory: {temp_dir}")


# Set up logging
def setup_logging():
    logging.basicConfig(filename='jlc2kicad.log', level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s')
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(levelname)s: %(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)

# Parse command-line arguments
def parse_arguments():
    parser = argparse.ArgumentParser(description='Generate KiCad library files from JLCPCB parts.')
    parser.add_argument('--lcsc_part_numbers', metavar='part_number', type=str, nargs='+',
                        help='LCSC part numbers to process', default='C2904912')
    parser.add_argument('--lib_dir', type=str, default='lib',
                        help='base directory for library files (default: lib)')
    parser.add_argument('--temp_dir', type=str, default='temp',
                        help='temporary directory for staging files (default: temp)')
    parser.add_argument('--sym_lib_table', type=str, default='sym-lib-table',
                        help='path to sym-lib-table file (default: sym-lib-table)')
    parser.add_argument('--fp_lib_table', type=str, default='fp-lib-table',
                        help='path to fp-lib-table file (default: fp-lib-table)')
    return parser.parse_args()

# Validate LCSC part numbers
def validate_part_numbers(part_numbers):
    pattern = r'^C\d{1,8}$'
    
    # Ensure part_numbers is always a list
    if isinstance(part_numbers, str):
        part_numbers = [part_numbers]
    
    trimmed_part_numbers = [part.strip() for part in part_numbers]
    valid_part_numbers = [part for part in trimmed_part_numbers if re.match(pattern, part)]
    invalid_part_numbers = set(trimmed_part_numbers) - set(valid_part_numbers)
    
    for part in invalid_part_numbers:
        logging.warning(f"Invalid LCSC part number: {part}. Skipping.")
    
    return valid_part_numbers


# Run JLC2KiCadLib tool
def run_jlc2kicadlib(lcsc_part, component_dir):
    try:
        subprocess.run(['JLC2KiCadLib', lcsc_part,
                        '-dir', component_dir,
                        '-symbol_lib_dir', component_dir,
                        '-footprint_lib', component_dir],
                       check=True)
        logging.info(f"Executed JLC2KiCadLib tool for {lcsc_part}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error running JLC2KiCadLib tool for {lcsc_part}: {str(e)}")
        return False
    return True



# Extract manufacturer part number from the "Value" property in the .kicad_sym file
def extract_mfr_part_number(component_dir):
    mfr_part = None
    for filename in os.listdir(component_dir):
        if filename.endswith('.kicad_sym'):
            with open(os.path.join(component_dir, filename), 'r') as f:
                content = f.read()
                value_line = next((line for line in content.splitlines() if 'property "Value"' in line), None)
                if value_line:
                    mfr_part = value_line.split('"')[3]
                    break
    return mfr_part

# Update the "Footprint" property in the .kicad_sym file
def update_footprint_property(component_dir, lib_dir, part_number):
    sym_filename = next((filename for filename in os.listdir(component_dir) if filename.endswith('.kicad_sym')), None)
    if sym_filename:
        sym_file_path = os.path.join(component_dir, sym_filename)
        with open(sym_file_path, 'r') as f:
            content = f.read()
        
        updated_content = re.sub(r'\(property "Footprint" ".*?"\)', f'(property "Footprint" "{lib_dir}/{part_number}/{part_number}_footprint.kicad_mod")', content)
        
        with open(sym_file_path, 'w') as f:
            f.write(updated_content)

# Process generated files
def process_generated_files(component_dir, lib_dir, part_number):
    for filename in os.listdir(component_dir):
        if filename.endswith('.step'):
            new_filename = f"{part_number}_model.step"
            dest_dir = os.path.join(lib_dir, part_number)
            os.makedirs(dest_dir, exist_ok=True)
            shutil.move(os.path.join(component_dir, filename), os.path.join(dest_dir, new_filename))
            logging.info(f"Moved {filename} to {dest_dir}")
        elif filename.endswith('.kicad_mod'):
            new_filename = f"{part_number}_footprint.kicad_mod"
            dest_dir = os.path.join(lib_dir, part_number)
            os.makedirs(dest_dir, exist_ok=True)
            shutil.move(os.path.join(component_dir, filename), os.path.join(dest_dir, new_filename))
            logging.info(f"Moved {filename} to {dest_dir}")
        elif filename.endswith('.kicad_sym'):
            new_filename = f"{part_number}_symbol.kicad_sym"
            dest_dir = os.path.join(lib_dir, part_number)
            os.makedirs(dest_dir, exist_ok=True)
            shutil.move(os.path.join(component_dir, filename), os.path.join(dest_dir, new_filename))
            logging.info(f"Moved {filename} to {dest_dir}")

# Update fp-lib-table
def update_fp_lib_table(fp_lib_table, lib_dir, processed_part_numbers):
    with open(fp_lib_table, 'a') as f:
        for part_number in processed_part_numbers:
            f.write(f"(lib (name \"{part_number}\")(type KiCad)(uri \"{lib_dir}/{part_number}\")(options \"\")(descr \"\"))\n")
    logging.info(f"Updated {fp_lib_table}")

# Update sym-lib-table
def update_sym_lib_table(sym_lib_table, lib_dir, processed_part_numbers):
    with open(sym_lib_table, 'a') as f:
        for part_number in processed_part_numbers:
            f.write(f"(lib (name \"{part_number}\")(type Legacy)(uri \"{lib_dir}/{part_number}/{part_number}_symbol.kicad_sym\")(options \"\")(descr \"\"))\n")
    logging.info(f"Updated {sym_lib_table}")

