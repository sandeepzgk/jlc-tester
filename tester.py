from helper import *

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
        
        update_footprint_property(component_dir, args.lib_dir, part_number)
        process_generated_files(component_dir, args.lib_dir, mfr_part)
    
    update_fp_lib_table(args.fp_lib_table, args.lib_dir, processed_part_numbers)
    update_sym_lib_table(args.sym_lib_table, args.lib_dir, processed_part_numbers)
    remove_temp_and_pycache(args.temp_dir)
    print("KiCad library generation completed successfully.")

if __name__ == '__main__':
    main()