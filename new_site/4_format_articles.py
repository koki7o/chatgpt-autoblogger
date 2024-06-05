def replace_newlines(input_string):
    # Replace '\n' with actual new lines
    output_string = input_string.replace("\\n", "\n")
    return output_string

# Example usage:
input_text = ""
output_text = replace_newlines(input_text)
print(output_text)