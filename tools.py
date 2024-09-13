import json
import os
import subprocess
import boto3
from datetime import datetime
import re
from collections import defaultdict


# Define the knowledge base ID
knowledge_base_id = "7VAQT5TQYM"

# Initialize Bedrock runtime clients
bedrock_runtime = boto3.client('bedrock-runtime', 'us-east-1')
bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', 'us-east-1')

def get_contexts_old(query, kbId, numberOfResults=5):
    """
    Retrieves contexts for a given query from the specified knowledge base.

    Args:
        query (str): The natural language query.
        kbId (str): The knowledge base ID.
        numberOfResults (int): Number of results to retrieve (default is 5).

    Returns:
        list: A list of contexts related to the query.
    """
    # Retrieve contexts for the query from the knowledge base
    results = bedrock_agent_runtime.retrieve(
        retrievalQuery={'text': query},
        knowledgeBaseId=kbId,
        retrievalConfiguration={'vectorSearchConfiguration': {'numberOfResults': numberOfResults}}
    )
    
    # Create a list to store the contexts
    contexts = [retrievedResult['content']['text'] for retrievedResult in results['retrievalResults']]
    
    return contexts



def get_contexts(query, kbId, numberOfResults=5):
    """
    Retrieves contexts for a given query from the specified knowledge base.

    Args:
        query (str): The natural language query.
        kbId (str): The knowledge base ID.
        numberOfResults (int): Number of results to retrieve (default is 5).

    Returns:
        list: A list of tuples containing contexts and their sources related to the query.
    """
    results = bedrock_agent_runtime.retrieve(
        retrievalQuery={'text': query},
        knowledgeBaseId=kbId,
        retrievalConfiguration={'vectorSearchConfiguration': {'numberOfResults': numberOfResults}}
    )
    
    contexts = [(retrievedResult['content']['text'], retrievedResult['location']['s3Location']['uri']) 
                for retrievedResult in results['retrievalResults']]
    
    return contexts


def call_claude_sonnet(prompt):
    """
    Calls the Claude Sonnet model with a given prompt.

    Args:
        prompt (str): The prompt to send to the model.

    Returns:
        str: The response from the model.
    """
    prompt_config = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }

    body = json.dumps(prompt_config)
    modelId = "anthropic.claude-3-sonnet-20240229-v1:0"
    accept = "application/json"
    contentType = "application/json"

    response = bedrock_runtime.invoke_model(body=body, modelId=modelId, accept=accept, contentType=contentType)
    response_body = json.loads(response.get("body").read())
    
    print (response_body)
    results = response_body.get("content")[0].get("text")
    return results

def claude_prompt_format(prompt: str) -> str:
    """
    Formats the prompt for the Claude model.

    Args:
        prompt (str): The original prompt.

    Returns:
        str: The formatted prompt.
    """
    return f"\n\nHuman: {prompt}\n\nAssistant:"

def call_claude(prompt):
    """
    Calls the Claude model with a formatted prompt.

    Args:
        prompt (str): The prompt to send to the model.

    Returns:
        str: The response from the model.
    """
    prompt_config = {
        "prompt": claude_prompt_format(prompt),
        "max_tokens_to_sample": 4096,
        "temperature": 0.7,
        "top_k": 250,
        "top_p": 0.5,
        "stop_sequences": [],
    }

    body = json.dumps(prompt_config)
    modelId = "anthropic.claude-v2"
    accept = "application/json"
    contentType = "application/json"

    response = bedrock_runtime.invoke_model(body=body, modelId=modelId, accept=accept, contentType=contentType)
    response_body = json.loads(response.get("body").read())

    results = response_body.get("completion")
    return results

def answer_query_old(user_input):
    """
    Answers a user query by retrieving context from Amazon Bedrock KnowledgeBases and calling an LLM.

    Args:
        user_input (str): The natural language question.

    Returns:
        str: The answer to the question based on context from the Knowledge Bases.
    """
    # Retrieve contexts for the user input from Bedrock knowledge bases
    userContexts = get_contexts_old(user_input, knowledge_base_id)

    # # Configure the prompt for the LLM
    # prompt_data = """
    # You are an AWS Solutions Architect and your responsibility is to answer user questions based on provided context.
    
    # Here is the context to reference:
    # <context>
    # {context_str}
    # </context>

    # Referencing the context, answer the user question.
    # <question>
    # {query_str}
    # </question>
    # """
    
     # Configure the prompt for the LLM
    prompt_data = """
    You are an virtual assistant and your responsibility is to answer user questions based on provided context.
    
    Here is the context to reference:
    <context>
    {context_str}
    </context>

    Referencing the context, answer the user question.
    <question>
    {query_str}
    </question>
    """
    formatted_prompt_data = prompt_data.format(context_str=userContexts, query_str=user_input)

    prompt = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "temperature": 0.5,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": formatted_prompt_data}
                ]
            }
        ]
    }
    
    json_prompt = json.dumps(prompt)
    response = bedrock_runtime.invoke_model(body=json_prompt, modelId="anthropic.claude-3-sonnet-20240229-v1:0",
                                            accept="application/json", contentType="application/json")
    response_body = json.loads(response.get('body').read())
    # print(response_body)
    answer = response_body['content'][0]['text']
    
    return answer

def iac_gen_tool(prompt):
    """
    Generates Infrastructure as Code (IaC) scripts based on a customer's request.

    Args:
        prompt (str): The customer's request.

    Returns:
        str: The S3 path where the generated IaC code is saved.
    """
    prompt_ending = "Act as a DevOps Engineer. Carefully analyze the customer requirements provided and identify all AWS services and integrations needed for the solution. Generate the Terraform code required to provision and configure each AWS service, writing the code step-by-step. Provide only the final Terraform code, without any additional comments, explanations, markdown formatting, or special symbols."
    generated_text = call_claude_sonnet(prompt + prompt_ending)
    
    # Save to S3
    s3 = boto3.client('s3')
    bucket_name = "bedrock-agent-generate-iac-estimate-cost"
    prefix = "iac-code/"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"iac_{timestamp}.tf"
    s3_path = f"{prefix}{filename}"
    
    # Write the Terraform code to a BytesIO object and upload it to S3
    from io import BytesIO
    file_buffer = BytesIO(generated_text.encode('utf-8'))
    s3.upload_fileobj(file_buffer, bucket_name, s3_path)
    
    return f"File saved to S3 bucket {bucket_name} at {s3_path}"

def iac_estimate_tool(prompt):
    """
    Estimates the cost of an AWS infrastructure using Infracost.

    Args:
        prompt (str): The customer's request.

    Returns:
        str: The cost estimation.
    """
    prompt_ending = "Given the estimated costs for an AWS cloud infrastructure, provide a breakdown of the monthly cost for each service. For services with multiple line items (e.g., RDS), aggregate the costs into a single total for that service. Present the cost analysis as a list, with each service and its corresponding monthly cost. Finally, include the total monthly cost for the entire infrastructure."
    
    # Get terraform code from S3
    s3 = boto3.client('s3')
    bucket_name = "bedrock-agent-generate-iac-estimate-cost"
    prefix_code = "iac-code"
    prefix_cost = "iac-cost"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"iac_cost_{timestamp}.tf"
    local_dir = '/tmp/infracost-evaluate'
    
    # Create the local directory if it doesn't exist
    os.makedirs(local_dir, exist_ok=True)

    # List objects in the S3 folder sorted by LastModified in descending order
    objects = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix_code)
    sorted_objects = sorted(objects['Contents'], key=lambda obj: obj['LastModified'], reverse=True)
    
    # Get the latest file key
    latest_file_key = sorted_objects[0]['Key']
    
    # Download the latest file
    local_file_path = os.path.join(local_dir, os.path.basename(latest_file_key))
    s3.download_file(bucket_name, latest_file_key, local_file_path)
    
    # Generate timestamp-based file name
    cost_filename = f"cost-evaluation-{timestamp}.txt"
    cost_file_path = f"/tmp/{cost_filename}"
    
    # Run Infracost CLI command
    infracost_cmd = f"infracost breakdown --path /tmp/infracost-evaluate > {cost_file_path}"
    try:
        subprocess.run(infracost_cmd, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        # Read the result file even if the command returns a non-zero exit code
        with open(cost_file_path, 'r') as f:
            cost_file = f.read()
        print(f"Infracost command returned non-zero exit code: {e.returncode}")
        print(f"Result: {cost_file}")
    else:
        with open(cost_file_path, 'r') as f:
            cost_file = f.read()
        print(f"Result: {cost_file}")
    
    # Upload cost evaluation file to S3 under the "iac-cost" folder
    s3_cost_result = os.path.join(prefix_cost, cost_filename)
    s3.upload_file(cost_file_path, bucket_name, s3_cost_result)
    
    generated_text = call_claude_sonnet(cost_file + prompt + prompt_ending)
    return generated_text

# def answer_query(user_input):
#     """
#     Answers a user query by retrieving context from Amazon Bedrock KnowledgeBases and calling an LLM.

#     Args:
#         user_input (str): The natural language question.

#     Returns:
#         str: The answer to the question based on context from the Knowledge Bases, including citations.
#     """
#     userContexts = get_contexts(user_input, knowledge_base_id)

#     context_str = "\n".join([f"Context {i+1}: {context[0]}\nSource: [{i+1}]" for i, context in enumerate(userContexts)])
#     sources_str = "\n".join([f"[{i+1}] {context[1]}" for i, context in enumerate(userContexts)])

#     prompt_data = """
#     You are a virtual assistant and your responsibility is to answer user questions based on provided context.
    
#     Here is the context to reference:
#     <context>
#     {context_str}
#     </context>

#     Referencing the context, answer the user question. Use citation numbers in square brackets [1], [2], etc. to cite your sources within the text. Do not include the full URLs in the main text.
#     <question>
#     {query_str}
#     </question>

#     After your answer, include a "References" section listing the full URLs for each citation, formatted as follows:

#     References:
#     {sources_str}
#     """
#     formatted_prompt_data = prompt_data.format(context_str=context_str, query_str=user_input, sources_str=sources_str)

#     prompt = {
#         "anthropic_version": "bedrock-2023-05-31",
#         "max_tokens": 4096,
#         "temperature": 0.5,
#         "messages": [
#             {
#                 "role": "user",
#                 "content": [
#                     {"type": "text", "text": formatted_prompt_data}
#                 ]
#             }
#         ]
#     }
    
#     json_prompt = json.dumps(prompt)
#     response = bedrock_runtime.invoke_model(body=json_prompt, modelId="anthropic.claude-3-sonnet-20240229-v1:0",
#                                             accept="application/json", contentType="application/json")
#     response_body = json.loads(response.get('body').read())
#     answer = response_body['content'][0]['text']
    
#     return answer

# def format_answer(answer):
#     """
#     Formats the answer to ensure only used references are included and properly displayed.

#     Args:
#         answer (str): The raw answer from the model.

#     Returns:
#         str: The formatted answer with proper References section, including only used references.
#     """
#     # Split the answer into main content and references
#     parts = re.split(r'\n(?:References|Referencias):\s*\n', answer, flags=re.IGNORECASE)
    
#     if len(parts) == 2:
#         main_content, references = parts
        
#         # Find all reference numbers used in the main content
#         used_refs = set(re.findall(r'\[(\d+)\]', main_content))
        
#         # Extract references and their numbers
#         ref_dict = defaultdict(list)
#         for ref in re.findall(r'\[(\d+)\]\s*(.*?)(?=\n\[|\Z)', references, re.DOTALL):
#             if ref[0] in used_refs:  # Only include references that are actually used
#                 ref_dict[ref[1].strip()].append(ref[0])
        
#         # Format references, combining duplicates and ensuring each is on a new line
#         formatted_references = []
#         for ref, numbers in ref_dict.items():
#             number_str = ', '.join(sorted(numbers, key=int))
#             formatted_references.append(f"[{number_str}] {ref}\n")
        
#         formatted_references_str = '\n'.join(formatted_references)
        
#         if formatted_references:
#             return f"{main_content.strip()}\n\nReferencias:\n\n{formatted_references_str}"
#         else:
#             return main_content.strip()  # Return only main content if no references were used
#     else:
#         return answer  # Return as is if no References section is found


def answer_query(user_input):
    """
    Answers a user query by retrieving context from Amazon Bedrock KnowledgeBases and calling an LLM.

    Args:
        user_input (str): The natural language question.

    Returns:
        dict: A dictionary containing the answer and the original context information.
    """
    userContexts = get_contexts(user_input, knowledge_base_id)

    context_str = "\n".join([f"Context {i+1}: {context[0]}" for i, context in enumerate(userContexts)])
    sources = [context[1] for context in userContexts]

    prompt_data = """
    You are a virtual assistant and your responsibility is to answer user questions based on provided context.
    
    Here is the context to reference:
    <context>
    {context_str}
    </context>

    Referencing the context, answer the user question. Use citation numbers in square brackets [1], [2], etc. to cite your sources within the text. The citation numbers should reflect the order in which you use them in your answer, not the order they appear in the context. Do not include the full URLs in the main text.
    <question>
    {query_str}
    </question>

    After your answer, include a "References" section listing only the reference numbers you used in your answer, without the URLs. For example:

    References:
    [1], [2], [3]
    """
    formatted_prompt_data = prompt_data.format(context_str=context_str, query_str=user_input)

    prompt = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "temperature": 0.5,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": formatted_prompt_data}
                ]
            }
        ]
    }
    
    json_prompt = json.dumps(prompt)
    response = bedrock_runtime.invoke_model(body=json_prompt, modelId="anthropic.claude-3-sonnet-20240229-v1:0",
                                            accept="application/json", contentType="application/json")
    response_body = json.loads(response.get('body').read())
    answer = response_body['content'][0]['text']
    
    return {"answer": answer, "sources": sources}

def format_answer(response):
    """
    Formats the answer to ensure references are properly numbered and displayed.

    Args:
        response (dict): A dictionary containing the answer and source information.

    Returns:
        str: The formatted answer with proper References section, including correctly numbered references.
    """
    answer = response["answer"]
    sources = response["sources"]
    
    # Split the answer into main content and references
    parts = re.split(r'\n(?:References|Referencias):\s*\n', answer, flags=re.IGNORECASE)
    
    if len(parts) == 2:
        main_content, _ = parts
        
        # Find all reference numbers used in the main content
        used_refs = re.findall(r'\[(\d+)\]', main_content)
        
        # Create a mapping of old reference numbers to new ones
        ref_map = {old: str(i+1) for i, old in enumerate(dict.fromkeys(used_refs))}
        
        # Replace old reference numbers with new ones in the main content
        for old, new in ref_map.items():
            main_content = main_content.replace(f'[{old}]', f'[{new}]')
        
        # Create the new references section
        new_references = []
        for i, ref_num in enumerate(ref_map.values()):
            if i < len(sources):
                new_references.append(f"[{ref_num}] {sources[i]}\n")
        
        formatted_references_str = '\n'.join(new_references)
        
        if formatted_references_str:
            return f"{main_content.strip()}\n\nReferencias:\n\n{formatted_references_str}"
        else:
            return main_content.strip()  # Return only main content if no references were used
    else:
        return answer  # Return as is if no References section is found