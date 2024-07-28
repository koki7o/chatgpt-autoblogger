import os
import time
import csv
import requests
from tqdm import tqdm
import concurrent.futures
import json
import random
from anthropic import APIError, APIConnectionError, APITimeoutError, RateLimitError, Anthropic, HUMAN_PROMPT, AI_PROMPT

# Load configuration from a JSON file
with open('config.json') as config_file:
    config = json.load(config_file)

# Set your Anthropic API key from the config file
ANTHROPIC_API_KEY = config["ANTHROPIC_API_KEY"]
print("Setting Anthropic API Key...")
# Initialize the Anthropic client
client = Anthropic(api_key=ANTHROPIC_API_KEY)

# Update your Freeimage.host API Key here from the config file
FREEIMAGE_HOST_API_KEY = config["FREEIMAGE_HOST_API_KEY"]

# Global list to store image URLs
image_urls = []


def upload_to_freeimage_host(image_path, Keyword):
    """
    Uploads an image to Freeimage.host with {Keyword} in the filename.
    Also stores the image URL in a global list.
    """
    print(f"Uploading {image_path} to Freeimage.host...")
    with open(image_path, 'rb') as image_file:
        files = {'source': image_file}
        data = {
            'key': FREEIMAGE_HOST_API_KEY,
            'action': 'upload',
            'format': 'json',
            'name': f'{Keyword}_image.png'  # Add {Keyword} in the filename
        }

        response = requests.post(
            'https://freeimage.host/api/1/upload', files=files, data=data, verify=Flase)

        if response.status_code == 200:
            url = response.json().get('image', {}).get('url', '')
            if url:
                print(f"Uploaded successfully: {url}")
                # Store both idea and URL
                image_urls.append({'idea': Keyword, 'url': url})
                return url
            else:
                print("Upload successful but no URL returned, something went wrong.")
        else:
            print(
                f"Failed to upload to Freeimage.host: {response.status_code}, {response.text}")
    return None



def clear_image_urls():
    """
    Clears the global list of image URLs.
    """
    global image_urls
    image_urls.clear()
    print("Cleared global image URLs.")


def claude_completion(prompt, max_tokens=1000, max_retries=5):
    """
    Send a completion request to Claude 3.5 Sonnet via the Anthropic API with retry logic.
    """
    for attempt in range(max_retries):
        try:
            response = client.completions.create(
                model="claude-3-sonnet-20240229",
                prompt=f"{HUMAN_PROMPT} {prompt}{AI_PROMPT}",
                max_tokens_to_sample=max_tokens,
                temperature=0.7,
            )
            return response.completion
        except (APIError, APIConnectionError, APITimeoutError) as e:
            if attempt == max_retries - 1:
                raise
            wait_time = (2 ** attempt) + random.uniform(0, 1)
            print(f"API error occurred: {str(e)}. Retrying in {wait_time:.2f} seconds...")
            print(e.__cause__) 
            time.sleep(wait_time)
        except RateLimitError as e:
            wait_time = int(e.retry_after) if hasattr(e, 'retry_after') else 60
            print(f"Rate limit reached. Waiting for {wait_time} seconds before retrying...")
            time.sleep(wait_time)
    
    raise Exception("Max retries reached. Unable to complete the request.")

def perplexity_research(Keyword, max_retries=3, delay=5):
    """
    Conducts perplexity research with retries on failure.
    Args:
        Keyword (str): The blog post idea to research.
        max_retries (int): Maximum number of retries.
        delay (int): Delay in seconds before retrying.
    Returns:
        dict or None: The response from the API or None if failed.
    """
    print(f"Starting perplexity research for: {Keyword}")
    url = "https://api.perplexity.ai/chat/completions"
    payload = {
        "model": config["perplexity_model"],
        "messages": [
            {
                "role": "system",
                "content": "Be precise and concise."
            },
            {
                "role": "user",
                "content": f"Find highly specific generalised data about {Keyword} in 2024. Do not give me any information about specific brands."
            }
        ]
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {config['PERPLEXITY_API_KEY']}"
    }

    for attempt in range(max_retries):
        response = requests.post(url, json=payload, headers=headers, verify=False)
        if response.status_code == 200:
            print("Perplexity research completed successfully.")
            try:
                return response.json()
            except ValueError:
                print("JSON decoding failed")
                return None
        else:
            print(
                f"Perplexity research failed with status code: {response.status_code}. Attempt {attempt + 1} of {max_retries}.")
            time.sleep(delay)

    print("Perplexity research failed after maximum retries.")
    return None


def get_internal_links(Keyword):
    with open(config["path_to_website_images"], "r") as f:
        brandimages_content = f.read()
    with open(config["path_to_links_file"], "r") as f:
        internal_links_content = f.read()
    
    prompt = f"""Read the following content and choose 5 relevant pages and their links that are relevant to {Keyword}. Don't have more than 5. Also choose 5 relevant product images to this article.

    Brand Images:
    {brandimages_content}

    Internal Links:
    {internal_links_content}
    """
    return claude_completion(prompt)


def create_data_vis(perplexity_research, Keyword):
    print("Creating data visualization descriptions...")
    
    prompt = f"""Based on the following research information about {Keyword}, describe 3 simple data visualizations that could be created to illustrate key points. For each visualization, provide:
    1. The type of chart or graph
    2. The data it would represent
    3. A brief description of what it would show

    Research information:
    {perplexity_research}

    Please be specific but concise in your descriptions.
    """
    
    visualizations = claude_completion(prompt, max_tokens=1000)
    
    print("Data visualization descriptions created successfully.")
    return visualizations

def process_blog_post(Keyword):
    print(f"Processing blog post for: {Keyword}")
    try:
        research_results = perplexity_research(Keyword)
        research_info = str(research_results)

        data_vis_descriptions = create_data_vis(research_info, Keyword)

        internal_links = get_internal_links(Keyword)

        with open(config["path_to_example_file_1"], "r") as f:
            example_file_1_content = f.read()
        with open(config["path_to_example_file_2"], "r") as f:
            example_file_2_content = f.read()

        outline_prompt = f"""Create a SHORT outline for a {config['page_type']} based on the following research:
        {research_info}
        
        Include relevant product images and internal links from the following:
        {internal_links}

        Also, consider incorporating these data visualization ideas:
        {data_vis_descriptions}
        """
        outline = claude_completion(outline_prompt)

        article_prompt = f"""Write a short, snappy article in {config['language']} at a grade 7 level based on the following outline:
        {outline}

        Use a {config['tone']} tone of voice. Write from a first person plural perspective for the business. 
        Include a key takeaway table at the top of the article, summarizing the main points. 
        Use markdown formatting and ensure to use tables and lists for formatting. 
        Include 3 relevant brand images and internal links maximum.

        Use these examples as references for the style and format:

        Example 1:
        {example_file_1_content}

        Example 2:
        {example_file_2_content}
        """
        article = claude_completion(article_prompt, max_tokens=2000)

        if article:
            print("Article created successfully.")
            clear_image_urls()
        else:
            print("Failed to create an article.")
        return outline, article
    except Exception as e:
        print(f"An error occurred while processing '{Keyword}': {str(e)}")
        return None, None

def process_keywords_concurrent():
    input_file = 'optimized_keywords.csv'
    output_file = 'processed_keywords.csv'

    fieldnames = ['Keyword', 'Outline', 'Article', 'Processed']

    with open(input_file, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        rows_to_process = [row for row in reader]

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_row = {executor.submit(process_blog_post, row['Keyword']): row for row in rows_to_process}

        progress = tqdm(concurrent.futures.as_completed(future_to_row), total=len(rows_to_process), desc="Processing Keywords")

        results = []
        for future in progress:
            row = future_to_row[future]
            try:
                outline, article = future.result()
                if outline is None or article is None:
                    processed_row = {
                        'Keyword': row['Keyword'],
                        'Outline': '',
                        'Article': '',
                        'Processed': 'Failed'
                    }
                else:
                    processed_row = {
                        'Keyword': row['Keyword'],
                        'Outline': outline,
                        'Article': article,
                        'Processed': 'Yes'
                    }
                results.append(processed_row)
            except Exception as exc:
                print(f'Keyword {row["Keyword"]} generated an exception: {exc}')
                processed_row = {
                    'Keyword': row['Keyword'],
                    'Outline': '',
                    'Article': '',
                    'Processed': 'Failed'
                }
                results.append(processed_row)

    with open(output_file, 'w', newline='', encoding='utf-8') as f_output:
        writer = csv.DictWriter(f_output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

# Example usage
if __name__ == "__main__":
    process_keywords_concurrent()