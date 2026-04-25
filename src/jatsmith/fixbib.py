import re

def validate_and_fix_bibtex(input_file, output_file):
    with open(input_file, "r", encoding="utf-8") as f:
        bib_data = f.readlines()

    corrected_data = []
    issues = []

    for line in bib_data:
        original_line = line  # Remember this line for reporting purposes

        # 1️⃣ Remove non-ASCII from BibTeX-keys
        match = re.match(r"(@\w+)\{([^,]*)", line)  
        if match:
            entry_type, bib_key = match.groups()
            fixed_bib_key = re.sub(r"([^\x00-\x7F])", "", bib_key) 
            if fixed_bib_key != bib_key:
                issues.append(f"❌ Removed non-ASCII from BibTeX key: {bib_key} → {fixed_bib_key}")
                line = line.replace(f"{{{bib_key}", f"{{{fixed_bib_key}", 1)

        # 2️⃣ Escape unescaped ampersands
        if "&" in line and not re.search(r"\\&", line):
            fixed_line = line.replace("&", r"\&")
            issues.append(f"❌ Escaped unescaped ampersands: {original_line.strip()} → {fixed_line.strip()}")
            line = fixed_line

        # 3️⃣ Replace `@data{` ofr`@dataset{` with `@misc{`
        if re.match(r"@data\s*\{", line, re.IGNORECASE) or re.match(r"@dataset\s*\{", line, re.IGNORECASE):
            fixed_line = re.sub(r"@data|@dataset", "@misc", line, flags=re.IGNORECASE)
            issues.append(f"❌ Replaced invalid entry type: {original_line.strip()} → {fixed_line.strip()}")
            line = fixed_line
        
        # 4️⃣ Remove spaces around the equal sign in key-value pairs
        fixed_line = re.sub(r"(\w+)\s*=\s*\{", r"\1={", line)
        if fixed_line != line:
            issues.append(f"❌ Removed spaces around '=': {original_line.strip()} → {fixed_line.strip()}")
            line = fixed_line

        # 5️⃣ Remove commented-out fields (lines starting with "%")
        if re.match(r"^\s*%", line):
            issues.append(f"❌ Removed commented-out field: {original_line.strip()}")
            continue  # Skip adding this line to the output

        corrected_data.append(line)

    # 6️⃣  Created corrected BibTeX file
    with open(output_file, "w", encoding="utf-8") as f:
        f.writelines(corrected_data)

    print(f"✅ Validation complete. Corrections saved in: {output_file}")
    if issues:
        print("\n🔍 **Found and corrected problems:**")
        for issue in issues:
            print(issue)
    else:
        print("✅ No errors found!")

def main():
    validate_and_fix_bibtex("bibliography.bib", "bibliography_fixed.bib")


if __name__ == "__main__":
    main()