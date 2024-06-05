import os
import openai
import time
import csv
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

# Initialize the OpenAI client
print("Initializing OpenAI client...")
client = openai.OpenAI()


# Create an Assistant
print("Creating OpenAI Assistant...")

args = (config['business_name'],
        config['business_type'],
        config['country'],
        config['language'])

assistant = client.beta.assistants.create(
    name="Content Creation Assistant",
    model="gpt-4o",
    instructions=''' You are SEOGPT, an AI that is profficient in SEO. 
    Your goal is to give best keywords for a business called {0}.
    It is a {1} business aimed at the population and consumers located in {2}. The keywords must be in {3}.
    '''.format(*args),
    tools=[{"type": "file_search"}, {"type": "code_interpreter"}],
)

print("Assistant created successfully.")


def wait_for_run_completion(thread_id, run_id, timeout=1200):
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


output_file = "./optimized_keywords.csv"


def get_keywords(thread_id, count=1):

    keywords = None

    get_request = '''Give me {0} keywords for this niche. Your goal is to come up with such keywords that
    are with low SEO difficulty, high search volume, low paid difficulty, low cost per click
    and suited for excellent ranking on Google. 
    It is very important to give me the keywords in a python list format, no new lines and no trailing new line.
    Like that: [keyword1, keyword2, keyword3, keyword4, keyword5, keyword6, keyword7, keyword8]. Also do not put the keywords in "" or in ''! '''.format(count)
    client.beta.threads.messages.create(
        thread_id=thread_id, role="user", content=get_request)
    get_request_run = client.beta.threads.runs.create(
        thread_id=thread_id, assistant_id=assistant.id)
    wait_for_run_completion(thread_id, get_request_run.id)

    messages = client.beta.threads.messages.list(thread_id=thread_id)

    keywords = next(
        (m.content[0].text.value for m in messages.data if m.role == "assistant"), None)

    if keywords:
        print("Keywords returned successfully.")
    else:
        print("Failed to get keywords.")

    return keywords

def process_keywords():
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_row = {executor.submit(get_keywords, client.beta.threads.create(
        ).id)}

        # Initialize tqdm progress bar
        progress = tqdm(concurrent.futures.as_completed(
            future_to_row), desc="Processing Keywords\n")

        # Regular expression pattern to match content between backticks
        pattern = r"(\[.*?\])"

        for future in progress:
            # Find all matches
            matches = re.findall(pattern, future.result(), re.DOTALL)
            for match in matches:
                keyword_list = match[1:-1].split(', ')

                # Write the list to the CSV file
                with open(output_file, 'w', newline='') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(['Keyword'])  # Write the header
                    writer.writerows([[keyword] for keyword in keyword_list]) 


if __name__ == "__main__":
    process_keywords()
