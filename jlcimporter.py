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
    logging.basicConfig(filename='jlc2kicad.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
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
        subprocess.run(['JLC2KiCadLib', lcsc_part, '-dir', component_dir],check=True)
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

# Update the "Model" property in the footprint kicad_mod file
def update_model_property_in_footprint(lib_dir, part_number):
    component_dir = os.path.join(lib_dir, part_number)
    kicad_mod_filename = next((f for f in os.listdir(component_dir) if f.endswith('.kicad_mod')), None)
    if not kicad_mod_filename:
        print(f"No .kicad_mod file found in {component_dir}.")
        return
    kicad_mod_file_path = os.path.join(component_dir, kicad_mod_filename)
    # Ensure that lib_dir format is correct for path concatenation
    normalized_lib_dir = lib_dir.strip("/").replace("\\", "/")
    new_model_path = f"${{KIPRJMOD}}/{normalized_lib_dir}/{part_number}/model.step"
    
    updated = False
    with open(kicad_mod_file_path, 'r') as file:
        lines = file.readlines()
    with open(kicad_mod_file_path, 'w') as file:
        for line in lines:
            if line.strip().startswith('(model'):
                # Find the end of the model path, assuming it ends before the first newline or space after "(model"
                end_of_path = line.find(')')  # Assuming the path does not contain ")"
                if end_of_path == -1:  # In case ")" is not found, which is unlikely
                    end_of_path = len(line)
                # Reconstruct the line with the new model path
                line = '(model ' + f'"{new_model_path}"' + line[end_of_path:] + '\n'
                updated = True
            file.write(line)
    
    if updated:
        print(f"Updated model property in {kicad_mod_filename} to {new_model_path}")
    else:
        print(f"No model property found to update in {kicad_mod_filename}.")         

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

# Update kicad_lib_table
def update_kicad_lib_table(lib_table, lib_dir, processed_part_numbers, lib_type):
    assert lib_type in ['sym', 'fp'], "lib_type must be either 'sym' for symbols or 'fp' for footprints"
    
    existing_parts = set()
    file_exists = os.path.isfile(lib_table)
    file_contents = []
    entry_template = {
        'sym': '  (lib (name "{0}")(type "KiCad")(uri "${{KIPRJMOD}}/{1}/{2}/symbol.kicad_sym")(options "")(descr ""))\n',  #format(part_number, lib_dir ,part_number)
        'fp': '  (lib (name "{0}")(type "KiCad")(uri "${{KIPRJMOD}}/{1}/{2}/footprint.kicad_mod")(options "")(descr ""))\n' #format(part_number, lib_dir ,part_number)
    }
    # Read the existing file or initialize it
    if file_exists:
        try:
            with open(lib_table, 'r') as f:
                file_contents = f.readlines()
        except FileNotFoundError:
            logging.warning(f"{lib_table} not found, will create a new one.")
    else:
        file_contents = [f"({lib_type}_lib_table\n", "  (version 7)\n"]
        logging.warning(f"{lib_table} not found, will create a new one.")
    # Extract existing part names and prepare file structure
    if file_contents and file_contents[-1].strip() == ")":
        file_contents.pop()  # Remove the closing parenthesis to append new entries later
    for line in file_contents:
        if "(lib (name" in line:
            part_name = line.split("\"")[1]
            existing_parts.add(part_name)
    # Add new entries if they do not exist
    for part_number in processed_part_numbers:
        if part_number not in existing_parts:
            new_entry = entry_template[lib_type].format(part_number, lib_dir ,part_number)
            file_contents.append(new_entry)
    # Ensure the structure is correctly closed and write back to the file
    if file_contents[-1].strip() != ")":
        file_contents.append(")\n")
    with open(lib_table, 'w' if file_exists else 'a') as f:
        f.writelines(file_contents)
    logging.info(f"Updated {lib_table} with new entries for {lib_type} library.")


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

# Main function
def main():
    setup_logging()
    args = parse_arguments()
    valid_part_numbers = validate_part_numbers(args.lcsc_part_numbers)
    create_directories(args.lib_dir, args.temp_dir)
    processed_part_numbers = []
    for part_number in valid_part_numbers:
        logging.info(f"Processing LCSC part number: {part_number}")
        lcsc_part = part_number
        component_dir = os.path.join(args.temp_dir, part_number)
        os.makedirs(component_dir, exist_ok=True)
        if not run_jlc2kicadlib(lcsc_part, component_dir):
            continue
        mfr_part = extract_mfr_part_number(component_dir+'/symbol')
        if mfr_part is None:
            logging.warning(f"Manufacturer part number not found for {lcsc_part}. Skipping.")
            continue
        part_number = f"{mfr_part}"
        processed_part_numbers.append(part_number)
        ## 2. Update the "Footprint" property in the symbol kicad_sym file
        ## 3. Update the HEADER section of the model step file so that it reflects the changes we have made so far (optional)
        process_generated_files(component_dir, args.lib_dir, mfr_part)
        update_model_property_in_footprint(args.lib_dir, mfr_part)
        update_kicad_lib_table(args.fp_lib_table, args.lib_dir, processed_part_numbers, 'fp')
        update_kicad_lib_table(args.sym_lib_table, args.lib_dir, processed_part_numbers, 'sym')
    remove_temp_and_pycache(args.temp_dir)
    print("KiCad library generation completed successfully.")



if __name__ == '__main__':
    main()