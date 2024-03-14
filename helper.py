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
                    help='LCSC part numbers to process', default=['C2904912', 'C2939725'])
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
                        '-dir', component_dir],
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
           mfr_part = filename.split('.')[0]
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
    for dirpath, dirnames, filenames in os.walk(component_dir):
        for filename in filenames:
            if filename.endswith('.step'):
                new_filename = f"model.step"
            elif filename.endswith('.kicad_mod'):
                new_filename = f"footprint.kicad_mod"
            elif filename.endswith('.kicad_sym'):
                new_filename = f"symbol.kicad_sym"
            else:
                # Skip files that do not match the expected extensions
                continue

            # Common operations for all file types
            dest_dir = os.path.join(lib_dir, part_number)
            os.makedirs(dest_dir, exist_ok=True)
            shutil.move(os.path.join(dirpath, filename), os.path.join(dest_dir, new_filename))
            logging.info(f"Moved {filename} from {dirpath} to {dest_dir}")

# Update fp-lib-table
def update_fp_lib_table(fp_lib_table, lib_dir, processed_part_numbers):
    existing_parts = set()
    file_contents = []
    file_exists = True

    # Try to read the existing file
    try:
        with open(fp_lib_table, 'r') as f:
            file_contents = f.readlines()
    except FileNotFoundError:
        logging.warning(f"{fp_lib_table} not found, will create a new one.")
        file_exists = False
        file_contents = ["(fp_lib_table\n", "  (version 7)\n"]

    # Extract existing part names and remove the closing parenthesis if present
    if file_exists:
        if file_contents[-1].strip() == ")":
            file_contents = file_contents[:-1]  # Remove the last line if it is just a closing parenthesis
        for line in file_contents:
            if "(lib (name" in line:
                part_name = line.split("\"")[1]
                existing_parts.add(part_name)

    # Add new parts
    new_entries = []
    for part_number in processed_part_numbers:
        if part_number not in existing_parts:
            new_entry = f'  (lib (name "{part_number}")(type "KiCad")(uri "${{KIPRJMOD}}/lib/{part_number}/footprint.kicad_mod")(options "")(descr ""))\n'
            new_entries.append(new_entry)

    # Update file contents if there are new entries
    if new_entries:
        file_contents.extend(new_entries)
        file_contents.append(")\n")  # Ensure the structure is correctly closed

        # Write the updated contents back to the file
        with open(fp_lib_table, 'w') as f:
            f.writelines(file_contents)

        logging.info(f"Updated {fp_lib_table} with new entries.")

# Update sym-lib-table
def update_sym_lib_table(sym_lib_table, lib_dir, processed_part_numbers):
    existing_parts = set()
    file_exists = os.path.isfile(sym_lib_table)
    file_is_empty = True if not file_exists or os.stat(sym_lib_table).st_size == 0 else False

    # Attempt to read existing parts if file exists
    if file_exists:
        try:
            with open(sym_lib_table, 'r') as f:
                content = f.readlines()
                for line in content:
                    if line.strip().startswith("(lib (name"):
                        part_name = line.split("\"")[1]
                        existing_parts.add(part_name)
        except FileNotFoundError:
            logging.warning(f"{sym_lib_table} not found, will create a new one.")

    # Prepare to append new entries or create the file with the correct structure
    with open(sym_lib_table, 'a') as f:
        if file_is_empty:
            f.write("(sym_lib_table\n  (version 7)\n")

        for part_number in processed_part_numbers:
            if part_number not in existing_parts:
                f.write(f'  (lib (name "{part_number}")(type "KiCad")(uri "${{KIPRJMOD}}/lib/{part_number}/symbol.kicad_sym")(options "")(descr ""))\n')

        if file_is_empty:
            f.write(")\n")

    logging.info(f"Updated {sym_lib_table} with new entries only.")


# Remove temp and __pycache__ directories
def remove_temp_and_pycache(temp_dir):
    for directory in [temp_dir, "__pycache__"]:
        try:
            shutil.rmtree(directory)
            logging.info(f"Removed directory: {directory}")
        except FileNotFoundError:
            logging.warning(f"Directory {directory} not found, nothing to remove.")
        except Exception as e:
            logging.error(f"Error removing directory {directory}: {str(e)}")
