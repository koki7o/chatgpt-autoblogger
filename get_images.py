import os
import csv
import json
import requests


# Load configuration from a JSON file
with open('config.json') as config_file:
    config = json.load(config_file)

PEXELS_API_KEY = config["PEXELS_API_KEY"]


def get_images(Keyword):
    url = f'https://api.pexels.com/v1/search?query={Keyword}&per_page=10'

    headers = { 
        'Authorization': PEXELS_API_KEY 
    }

    r = requests.get(url, headers=headers, verify=False)
    
    response = json.loads(r.content)
    photos = response['photos']
    with open('brandimagesandlinks.txt', 'a', newline='') as f_output:
        for photo in photos:
            f_output.write(photo['url']+'\n')


input_file = 'optimized_keywords.csv'

# Read all rows to be processed
with open(input_file, newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    rows_to_process = [row for row in reader]

    # Process each blog post idea concurrently
    for row in rows_to_process:
        get_images(row['Keyword'])
