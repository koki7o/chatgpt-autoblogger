import os
import openai
import time
import csv
import requests
from tqdm import tqdm
import concurrent.futures
import json
import re

# Load configuration from a JSON file
with open('config.json') as config_file:
    config = json.load(config_file)

# Set your OpenAI API key from the config file
OPENAI_API_TOKEN = config["OPENAI_API_TOKEN"]
print("Setting OpenAI API Key...")
os.environ["OPENAI_API_KEY"] = OPENAI_API_TOKEN

# Update your Freeimage.host API Key here from the config file
FREEIMAGE_HOST_API_KEY = config["FREEIMAGE_HOST_API_KEY"]

# Initialize the OpenAI client
print("Initializing OpenAI client...")
client = openai.OpenAI()

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
            'https://freeimage.host/api/1/upload', files=files, data=data, verify=False)

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


def upload_file(file_path, purpose):
    print(f"Uploading file: {file_path} for purpose: {purpose}")
    with open(file_path, "rb") as file:
        response = client.files.create(file=file, purpose=purpose)
    print(f"File uploaded successfully, ID: {response.id}")
    return response.id


def clear_image_urls():
    """
    Clears the global list of image URLs.
    """
    global image_urls
    image_urls.clear()
    print("Cleared global image URLs.")


print("Commencing file uploads...")
# Upload your files using paths from the config file
internal_links_file_id = upload_file(
    config["path_to_links_file"], 'assistants')
content_plan_file_id = upload_file(config["path_to_plan_csv"], 'assistants')
brand_plan_file_id = upload_file(
    config["path_to_example_file_1"], 'assistants')
images_file_id = upload_file(config["path_to_website_images"], 'assistants')

# Create an Assistant
print("Creating OpenAI Assistant...")
assistant = client.beta.assistants.create(
    name="Content Creation Assistant",
    model="gpt-4o",
    instructions=f"""
        You are SEOWriterGPT - an expert in writing SEO-optimized content that ranks highly on Google. Your task is to create engaging, fresh, unique content with optimized titles, using clear and simple English suitable for a grade 11 reading level.

        - Content must be fresh, not duplicative, rich in relevant entities, focused on one user intent, high effort, and credit original sources.
        - Use canonical forms of words instead of slang.
        - Ensure high-quality user-generated content (UGC) and expert authorship.
        - Do not conclude the content until the final generation.
        - You are writing for {config['business_name']}.
        - Use product images and internal links from {config['path_to_website_images']} and {config['path_to_links_file']}. Embed them in the final article using markdown.
        - Never invent internal links or image links.
        - Include internal links from {config['path_to_links_file']}.
        - Use retrieval and code_interpreter as instructed.
        - The final content must include internal links and embedded product images from {config['path_to_website_images']} with proper formatting.

        Steps:
        1. Read {config['path_to_website_images']} to get images, create visualizations, and store them for the final article.
        2. Find relevant brand images from {config['path_to_website_images']}, create an outline, then write an article with all gathered data.
        3. Copy the tone from {config['path_to_example_file_1']}, {config['path_to_example_file_2']}, and the article [on Growth Memo](https://www.growth-memo.com/p/2596).
        4. Follow the tone and style of the provided examples for {config['page_type']}.
        5. Ensure the article is written at a grade 7 reading level in {config['language']}.
        6. Every blog post should include at least 3 product images and internal links to other pages from {config['business_name']}.
        7. Ensure all links are accurate and relevant, avoiding low-quality pages and domains.
        8. Avoid aggressive anchor text and ensure title match and relevance between source and linked documents.
        9. Use links from new and trusted pages and include brand mentions.

        First, read the attached files and create a detailed outline for a {config['page_type']}. Include up to 3 highly relevant internal collection links and brand image links.
    """,
    tools=[{"type": "file_search"}, {"type": "code_interpreter"}],
    tool_resources={
        "code_interpreter": {
            "file_ids": [internal_links_file_id, content_plan_file_id,
                         brand_plan_file_id, images_file_id]
        }
    }
)

print("Assistant created successfully.")


def wait_for_run_completion(thread_id, run_id, timeout=1000):
    print(
        f"Waiting for run completion, thread ID: {thread_id}, run ID: {run_id}")
    start_time = time.time()
    while time.time() - start_time < timeout:
        run_status = client.beta.threads.runs.retrieve(
            thread_id=thread_id, run_id=run_id)
        if run_status.status == 'completed':
            print("Run completed successfully.")
            return run_status
        time.sleep(10)
    raise TimeoutError("Run did not complete within the specified timeout.")


def perplexity_research(Keyword, max_retries=3, delay=5, Year=2024):
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
        "model": "pplx-70b-online",
        "messages": [
            {
                "role": "system",
                "content": "Be precise and concise."
            },
            {
                "role": "user",
                "content": f"""
                    Find highly specific data about {Keyword} in {Year}. 
                    Give also the sources for the information.
                """
            }
        ]
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {config['PERPLEXITY_API_KEY']}"
    }

    for attempt in range(max_retries):
        response = requests.post(
            url, json=payload, headers=headers, verify=False)
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


def get_internal_links(thread_id, Keyword):
    print(f"Fetching internal links relevant to: {Keyword}")
    get_request = f"Use file_search. Read internal_links.txt, Choose 5 relevant pages and their links, that are relevant to {Keyword}. Don't have more than 3. Now read brandimages.txt - choose 3 relevant product images to this article"
    client.beta.threads.messages.create(
        thread_id=thread_id, role="user", content=get_request)
    get_request_run = client.beta.threads.runs.create(
        thread_id=thread_id, assistant_id=assistant.id)
    wait_for_run_completion(thread_id, get_request_run.id)
    messages = client.beta.threads.messages.list(thread_id=thread_id)
    print("Internal links fetched successfully.")
    return next((m.content for m in messages.data if m.role == "assistant"), None)


def create_data_vis(thread_id, perplexity_research, Keyword):
    print("Creating data visualizations...")
    for _ in range(3):  # Loop to generate 3 visualizations
        get_request = f"""
            Use Code Interpreter - invent a Visualization of some interesting data from {perplexity_research} 
            and add the sources used for the visualization.
        """
        client.beta.threads.messages.create(
            thread_id=thread_id, role="user", content=get_request)
        get_request_run = client.beta.threads.runs.create(
            thread_id=thread_id, assistant_id=assistant.id)
        wait_for_run_completion(thread_id, get_request_run.id)

        messages = client.beta.threads.messages.list(thread_id=thread_id)

        if hasattr(messages.data[0].content[0], 'image_file'):
            file_id = messages.data[0].content[0].image_file.file_id

            image_data = client.files.content(file_id)
            image_data_bytes = image_data.read()

            image_path = f"./visualization_image_{_}.png"
            with open(image_path, "wb") as file:
                file.write(image_data_bytes)

            print(f"Visualization {_+1} created, attempting upload...")
            upload_to_freeimage_host(image_path, Keyword)
        else:
            print(
                f"No image file found in response for visualization {_+1}. Attempt aborted.")


def elaborate_chapter(thread_id, chapter, outline, Keyword):
    """
    Elaborates on a given chapter using OpenAI API.
    Args:
        thread_id (str): The thread ID.
        chapter (str): The chapter to elaborate.
    Returns:
        str: The elaborated chapter.
    """
    print(
        f"Elaborating on chapter: {chapter[:50]}...")  # Print the first 50 characters of the chapter
    chapter_request = f"""
        Elaborate more on the following chapter {chapter}. Use at least 400 words. Do not add an explicit conclusion section for the chapter.

        - Consider the complete {outline} and ensure that you are writing the chapter in alignment with it.
        - Retain all images, links, and visualizations currently in the chapter.
        - Preserve the existing sources as external links.
        - Focus on the {Keyword} for which the entire article is written.
        - Use simple language and avoid overly creative or informal language.
        - Write with a {config['tone']} tone, similar to The Guardian newspaper, providing straightforward information.
        - Use a first-person plural perspective for the business.
        - Maintain all existing formatting, links, and images.
        - Do not introduce new images or internal links; use those already in the chapter.
        - Keep the research that was already conducted in the chapter.
        - Write the text in a scientific, lecture-book style, not as storytelling.
        - Ensure the content is detailed and written at a grade 7 reading level.
        - The tone must be {config['tone']}.

        Ensure the chapter is specific and scientific, adhering to the provided guidelines
    """
    client.beta.threads.messages.create(
        thread_id=thread_id, role="user", content=chapter)
    elaborate_run = client.beta.threads.runs.create(
        thread_id=thread_id, assistant_id=assistant.id)
    wait_for_run_completion(thread_id, elaborate_run.id)
    messages = client.beta.threads.messages.list(thread_id=thread_id)
    elaborated_chapter = next(
        (m.content for m in messages.data if m.role == "assistant"), None)
    return elaborated_chapter


def process_blog_post(thread_id, Keyword):
    print(f"Processing blog post for: {Keyword}")
    research_results = perplexity_research(Keyword)
    research_info = str(research_results)

    create_data_vis(thread_id, research_info, Keyword)

    internal_links = get_internal_links(thread_id, Keyword)

    # Only include relevant image URLs for the current blog post idea
    relevant_image_urls = [img['url']
                           for img in image_urls if img['idea'] == Keyword]
    images_for_request = " ".join(relevant_image_urls)

    outline_request = f"""
        Use file_search to review brandimages.txt and internal_links.txt. Create a concise outline for a {config['page_type']} based on {perplexity_research}. Include sources for the data from {perplexity_research}. 

        - Include data visualizations from {create_data_vis}.
        - Do not invent image links.
        - Use product images from brandimages.txt and internal links from {internal_links}.
        - Include custom graphs from {images_for_request}.

        The outline should place relevant product images and internal links in appropriate sections. Each article needs a minimum of 3 brand images and internal links.
    """

    client.beta.threads.messages.create(
        thread_id=thread_id, role="user", content=outline_request)
    outline_run = client.beta.threads.runs.create(
        thread_id=thread_id, assistant_id=assistant.id)
    wait_for_run_completion(thread_id, outline_run.id)
    messages = client.beta.threads.messages.list(thread_id=thread_id)
    outline = next(
        (m.content for m in messages.data if m.role == "assistant"), None)

    article = None
    if outline:
        article_request = f"""
            Include images from {get_internal_links} and write a 1500-word detailed, informative article in {config['language']}.

            - Write 20 titles with 2 paragraphs each.
            - Use formatting such as tables, embeds, internal links, and lists.
            - Write at a grade 7 reading level, ensuring the article is detailed and well-explained.
            - Only use internal links from {internal_links}.
            - Never invent internal links or image links.
            - Include images from {create_data_vis} and real internal links from internal_links.txt.
            - Follow the outline: {outline}.

            The article should:
            - Use a mix of {images_for_request} and brand images from brandimages.txt.
            - Include external links to sources from {perplexity_research}.
            - Use specific information from {research_results} with footnotes.
            - Employ a {config['tone']} tone, similar to The Guardian newspaper, and avoid overly creative language.
            - Be written from a first-person plural perspective for the business.
            - Start with a key takeaway table summarizing the main points.
            - Include 3 relevant internal links and brand images naturally within the content.

            The final product should be a well-formatted pillar page following the provided outline and examples.
        """
        client.beta.threads.messages.create(
            thread_id=thread_id, role="user", content=article_request)
        article_run = client.beta.threads.runs.create(
            thread_id=thread_id, assistant_id=assistant.id)
        wait_for_run_completion(thread_id, article_run.id)
        messages = client.beta.threads.messages.list(thread_id=thread_id)
        article = next(
            (m.content for m in messages.data if m.role == "assistant"), None)

    # ellaborated_article = None

    # if article:
    #     # Split the article into chapters
    #     chapters = re.split(r'\n## ', article[0].text.value)  # Assuming chapters are separated by '## '
    #     # Remove the first empty string if exists
    #     if chapters and not chapters[0]:
    #         chapters.pop(0)

    #     # Elaborate on each chapter
    #     ellaborated_article = chapters[0]
    #     for chapter in chapters[1:]:
    #         try:
    #             elaborated_chapter = elaborate_chapter(thread_id, chapter, outline, Keyword)

    #             # Replace the original chapter with the elaborated chapter
    #             ellaborated_article += '\n##' + elaborated_chapter[0].text.value
    #         except Exception as exc:
    #             print(f'Chapter "{chapter[:50]}" generated an exception: {exc}')

    #     print("Article created successfully.")
    #     clear_image_urls()  # Call the new function here to clear the image URLs
    # else:
    #     print("Failed to create an article.")
    return outline, article  # , ellaborated_article


def process_keywords_concurrent():
    input_file = 'optimized_keywords.csv'
    output_file = 'processed_keywords.csv'

    # Corrected fieldnames array to include a missing comma and ensure it matches expected output
    fieldnames = ['Keyword', 'Outline', 'Article', 'Processed']

    # Read all rows to be processed
    with open(input_file, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        rows_to_process = [row for row in reader]

    # Process each blog post idea concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_row = {executor.submit(process_blog_post, client.beta.threads.create(
        ).id, row['Keyword']): row for row in rows_to_process}

        # Initialize tqdm progress bar
        progress = tqdm(concurrent.futures.as_completed(future_to_row), total=len(
            rows_to_process), desc="Processing Keywords")

        # Collect results first to avoid writing to the file inside the loop
        results = []
        for future in progress:
            row = future_to_row[future]
            try:
                # Assuming this returns an outline and an article
                outline, article = future.result()
                # Create a new dictionary for CSV output to ensure it matches the specified fieldnames
                processed_row = {
                    'Keyword': row['Keyword'],
                    'Outline': outline,
                    'Article': article,
                    'Processed': 'Yes'
                }
                results.append(processed_row)
            except Exception as exc:
                print(
                    f'Keyword {row["Keyword"]} generated an exception: {exc}')
                # Handle failed processing by marking as 'Failed' but still match the fieldnames
                processed_row = {
                    'Keyword': row['Keyword'],
                    'Outline': 'Failed',  # or you might use 'N/A' or similar placeholder
                    'Article': 'Failed',
                    'Processed': 'Failed'
                }
                results.append(processed_row)

    # Write all results to the output file after processing
    # Use 'w' to overwrite or create anew
    with open(output_file, 'w', newline='', encoding='utf-8') as f_output:
        writer = csv.DictWriter(f_output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)


# Example usage
if __name__ == "__main__":
    process_keywords_concurrent()
