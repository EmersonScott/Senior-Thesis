from config import gpt_model, gpt_temp
import json
from PIL import Image
import base64
import io
import re
#Function that takes a list of blocks in order of the tower [red, green, blue] and produces a prompt to be given to the GPT4o in sideview
#https://platform.openai.com/docs/guides/structured-outputs/examples
def get_state_querry_prompt():
    system_prompt = ("""
You are a a 6 DoF robot with basic pick and place capabilities. Your task is to analyze the scene, determine the objects present, and infer their relationships through detailed chain of thought reasoning.

# Instructions

You should output a JSON object containing the following fields:

- **objects**: A list of all objects visible in the scene that are relevant to a pick and place task. Make sure to include the table as one of the objects.
  
- **object_relationships**: A list of tuples describing relationships between the objects. Each tuple should be in the format `<OBJECT1, OBJECT2>`, where `OBJECT1` is directly on top of `OBJECT2`. Include relationships where the objects are directly on the table. Do not include transitive relationships; for example, if block A is on block B and block B is on the table, do not state that block A is on the table.

Ensure that every object is on at least one other object or the table. No object should be unplaced. 

# Chain of Thought Reasoning

1. **Identify Objects**: Begin by analyzing the scene to identify all visible objects relevant to the pick and place task. This includes objects and the table itself.
  
2. **Determine Object Positions**: For each object, determine its placement in relation to other objects:
   - Is the object on another object or on the table?
   - Make sure no object is left unplaced.

3. **Establish Relationships**: Once object positions are determined, establish relationships following these rules:
   - Record relationships where one object is directly on top of another.
   - Each relationship is a pair `<OBJECT1, OBJECT2>`, where `OBJECT1` is directly above `OBJECT2`.
   - Avoid transitive relationships to ensure clarity. 

4. **Verify Completeness**: Ensure that all objects are covered in the relationships and that none remain without being stacked or placed on the table.

# Output Format

Your output should be formatted as a JSON object, like the example below:

```json
{
  "objects": ["table", "object A", "object B", "object C"],
  "object_relationships": [["object A", "object B"], ["object B", "table"], ["object C", "table"]]
}
```

Make sure the output JSON adheres strictly to the specified structure and validates that each object is accounted for in the relationships.

# Examples

**Input Scene Description**:
- object A is on object B.
- object B is on the table.
- object C is also on the table.

**Chain of Thought Reasoning**:
1. Identify Objects: The scene includes "Object A", "Object B", "Object C", and the "table".
2. Determine Object Positions:
   - Object A is on Object B.
   - Object B is on the table.
   - Object C is on the table.
3. Establish Relationships:
   - `<Object A, Object B>`
   - `<Object B, Table>`
   - `<Object C, Table>`

**Output JSON**:
```json
{
  "objects": ["table", "Object A", "Object B", "Object C"],
  "object_relationships": [["Object A", "Object B"], ["Object B", "table"], ["Object C", "table"]]
}
```

# Notes

- The table itself should also be visible in the object list.
- Ensure no object is left unplaced; every object must be included in the relationships field either on another object or on the table.
- Follow the reasoning steps explicitly before outputting to ensure correctness and completeness.
""")
    user_prompt = f"Give me the state in the given image"
    return system_prompt, user_prompt

def get_task_initerpretation_prompt():
    user_prompt = ("""
You are a 6 DoF UR5 robot arm equipped with a traditional gripper, with pick and place capabilities.\n
Based on the contents you see in front of you (see image), as seen through a camera in your gripper, what general task might you most likely be intended to perform?\n
If intentions are unclear but you see a task that you are equipped to complete that might be helpful to the user anyway, return that.\n
If no meaningful tasks stand out, return ‘No meaningful tasks detected.’\n
Make sure to return exactly one definitive task - if multiple options are equally viable, choose one at random.\n
Makes sure the response is as concise as possible, as it will be received by another task planning LLM for further processing and execution.
                     """)
    return user_prompt

def get_basic_prompt(obj_and_relationships, task_interpretation):
    """
    Constructs a string prompt for a language model (LLM) to determine the next best move 
    to transition from the start state to the end state in a block world scenario.

    Args:
        start_state (dict): A dictionary representing the initial positions of blocks. 
                            Keys are block names, and values are their placements.
        end_state (dict): A dictionary representing the desired final positions of blocks. 
                          Keys are block names, and values are their placements.

    Returns:
        str: A formatted string prompt describing the start state, the desired end state, 
             and a json for the next best move to transition from the start state to the end state.
             the json should have fields 
    """

    start_state = {relationship[0]: relationship[1] for relationship in obj_and_relationships["object_relationships"]}
    # end_state = {end_tower_list[i+1]: end_tower_list[i] for i in range(len(end_tower_list)-1)}
    print(f"{start_state=}")
    # print(f"{end_state=}")

    # Construct string prompt for an LLM
    prompt = f"""\nYour task is to\n"""
    prompt += f"{task_interpretation}\n"

    prompt += f"""\nGiven the current state:\n"""
    for block, placement in start_state.items():
        prompt += f"   {block} is on {placement}\n"

    prompt+="\n"

    # prompt += """and desired end state:\n"""
    # for block, placement in end_state.items():
    #     prompt += f"   {block} is on {placement}\n"

    # prompt+= "\n"

    prompt +="""what is the next best move (single pick and place operation) to get us closer to completing the task from the start state?
    The place location can be another object (prefered), or a defined region on the table if one exists, e.g. 'blue square'.
    Your answer needs to have two parts on two seperate lines.

   pick: *object to be picked up*
   place: *object or location to put the picked object on*

if there is no object to move please have
   pick: None
   place: None
    """
    
    print(f"{prompt=}")
    return prompt


#helper function that formats the image for GPT api
def encode_image(img_array):
    # Convert the ndarray to a PIL Image
    image = Image.fromarray(img_array)
    
    # Create a BytesIO object to save the image
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG")  # Specify the format you want
    buffered.seek(0) #Possibly not needed
    # Get the byte data and encode to base64
    encoded_string = base64.b64encode(buffered.read()).decode('utf-8')
    
    return encoded_string


def get_task_interpretation(client, rgb_image1, rgb_image2):
    img_type = "image/jpeg"

    # TASK INTERPRETER
    task_interpretation_prompt = get_task_initerpretation_prompt()

    task_interpretation_response = client.chat.completions.create(
        model=gpt_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": task_interpretation_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{img_type};base64,{encode_image(rgb_image1)}"}},
                    {"type": "image_url", "image_url": {"url": f"data:{img_type};base64,{encode_image(rgb_image2)}"}}
                ]
            },
        ],
        response_format={"type": "text"},
        temperature=gpt_temp
    )
    task_interpretation = task_interpretation_response.choices[0].message.content
    print("TASK INTERPRETATION:", task_interpretation)
    return task_interpretation


#api calling function
def get_gpt_next_instruction(client, rgb_image, task_interpretation, action_history, previous_plan):
    image = encode_image(rgb_image)
    img_type = "image/jpeg"


    # STATE INTERPRETER
    state_querry_system_prompt, state_querry_user_prompt = get_state_querry_prompt()
    #print(f"{state_querry_system_prompt=}")
    #print()
    #print(f"{state_querry_user_prompt=}")
    #print()
    state_response = client.chat.completions.create(
        model=gpt_model,
        messages=[
            { "role": "system", "content":[{"type": "text", "text":f"{state_querry_system_prompt}"}]},  # Only text in the system message
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": state_querry_user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{img_type};base64,{encode_image(rgb_image)}"}}
                ]
            },
        ],
        response_format={"type": "json_object"},
        temperature=gpt_temp
    )
    state_json = json.loads(state_response.choices[0].message.content) # extract JSON from reposnse and convert to python dictionary
    #instruction_system_prompt, instruction_user_prompt = get_instruction_prompt(desired_tower_order, state_json, action_history, previous_plan)


    # INSTRUCTION GENERATOR
    instruction_user_prompt = get_basic_prompt(state_json, task_interpretation) # new prompt call, instruction_system_prompt no longer used
    #print(f"{instruction_system_prompt=}")
    #print()
    #print(f"{instruction_user_prompt}")
    #print()
    #print(f"{instruction_assitant_prompt=}")
    instruction_response = client.chat.completions.create(
        model=gpt_model,
        messages=[
            #{ "role": "system", "content":[{"type": "text", "text":f"{instruction_system_prompt}"}]},
            #{ "role": "assistant", "content":[{"type": "text", "text":f"{instruction_assitant_prompt}"}]},
            { "role": "user", "content":[{"type": "text", "text":f"{instruction_user_prompt}"}]}
        ],
        response_format={"type": "text"},
        temperature=gpt_temp
    )
    instruction_response = instruction_response.choices[0].message.content
    pattern = r"pick:\s*(.*)\s*place:\s*(.*)"
    match = re.search(pattern, instruction_response)
    pick = match.group(1).strip()
    place = match.group(2).strip()

    
    # Determine the value of done
    done = 0 if pick != "None" or place != "None" else 1
    
    # Create the JSON object
    instruction_json = {
        "pick": pick,
        "place": place,
        "done": done
    }

    #min_key = min(instruction_json.keys(), key=lambda x: int(x))
    #next_instruction_json = instruction_json.pop(min_key)
    #future_instructions_json = [(k,v) for k, v in sorted(instruction_json.items(), key=lambda item: item[0])]
    next_instruction_json = instruction_json
    future_instructions_json = None
    instruction_system_prompt = None
    return (state_response, state_json, state_querry_system_prompt, state_querry_user_prompt), (instruction_response, next_instruction_json, future_instructions_json, instruction_system_prompt, instruction_user_prompt)
    
def print_json(j, name=""):
    out_str = f"{name}={json.dumps(j, indent=4)}"
    print(out_str)
    return out_str


if __name__ == "__main__":
    from FoundationModelBlockStacking.APIKeys import API_KEY
    from control_scripts import goto_vec, get_pictures
    from magpie_control import realsense_wrapper as real
    from magpie_control.ur5 import UR5_Interface as robot
    from config import sideview_vec
    import matplotlib.pyplot as plt
    from openai import OpenAI

    myrs = real.RealSense()
    myrs.initConnection()
    myrobot = robot()
    print(f"starting robot from gpt planning")

    myrobot.start()
    myrobot.open_gripper()

    client = OpenAI(
        api_key= API_KEY,
    )
    goto_vec(myrobot, sideview_vec)
    rgb_img, depth_img = get_pictures(myrs)

    

    ##--string for GPT QUERY--##
    tower = ["green block", "blue block", "yellow block"]
    action_history = []
    previous_plan = []
    for i in range(2):
        (state_response, state_json, _, _), (instruction_response, next_instruction, future_instructions, _, _) = get_gpt_next_instruction(client, rgb_img, tower, action_history, previous_plan)
        print("\n\n")
        print_json(state_json, name="state")
        print()
        print_json(next_instruction, name="next instruction")
        print()
        print_json(future_instructions, name="plan")
        action_history.append(next_instruction)
        previous_plan = future_instructions
        

    #print(f"{dir(myrobot)=}")
    #print(f"{dir(myrs)=}")
    myrobot.stop()
    myrs.disconnect()
    plt.figure()
    plt.imshow(rgb_img)
    plt.show(block = False)
    input()