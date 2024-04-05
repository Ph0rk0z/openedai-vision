import io
import uuid
import requests
from datauri import DataURI
from PIL import Image
import torch
from typing import Optional, List, Literal
from pydantic import BaseModel

class ImageURL(BaseModel):
    url: str
    detail: Optional[str] = "auto" # auto -> low (512) or high (Nx512) based on res.

class Content(BaseModel):
    type: Literal["text", "image_url"]
    text: Optional[str] = None
    image_url: Optional[ImageURL] = None

class Message(BaseModel):
    role: str
    content: List[Content]

class ImageChatRequest(BaseModel):
    model: str # = "gpt-4-vision-preview"
    messages: List[Message]
    max_tokens: int = 512

class VisionQnABase:
    model_name: str = None
    format: str = None
    revision: str = 'main'
    
    def __init__(self, model_id: str, device: str, extra_params = {}, format = None):
        self.device, self.dtype = self.select_device_dtype(device)

        self.params = {
            'pretrained_model_name_or_path': model_id,
            'torch_dtype': self.dtype,
            'low_cpu_mem_usage': True,
            'revision': self.revision,
            'device_map': 'auto' if device == 'auto' else self.device,
        }
        if extra_params.get('load_in_4bit', False):
            load_in_4bit_params = {
                'quantization_config': {
                    'load_in_4bit': True,
                    'bnb_4bit_quant_type': "nf4",
                    'bnb_4bit_use_double_quant': True,
                    'bnb_4bit_compute_dtype': self.dtype,
                }
            }
            self.params.update(load_in_4bit_params)
        elif extra_params.get('load_in_8bit', False):
            load_in_8bit_params = {
                'quantization_config': {
                    'load_in_8bit': True,
                }
            }
            self.params.update(load_in_8bit_params)

        if extra_params.get('use_flash_attn', False):
            flash_attn_params = {
                "attn_implementation": "flash_attention_2",
            }
            self.params.update(flash_attn_params)

        if extra_params.get('trust_remote_code', False):
            flash_attn_params = {
                "trust_remote_code": True,
            }
            self.params.update(flash_attn_params)

        if format:
            self.format =  format
        

    def select_device(self):
        return 'cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu'

    def select_dtype(self, device):
        return torch.float32 if device == 'cpu' else torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16

    def select_device_dtype(self, device):
        device = self.select_device() if device == 'auto' else device
        dtype = self.select_dtype(device)
        return device, dtype
    
    async def chat_with_images(self, messages: list[Message], max_tokens: int) -> str:
        pass

async def url_to_image(img_url: str) -> Image.Image:
    if img_url.startswith('http'):
        response = requests.get(img_url)
        
        img_data = response.content
    elif img_url.startswith('data:'):
        img_data = DataURI(img_url).data

    return Image.open(io.BytesIO(img_data)).convert("RGB")

async def url_to_file(img_url: str) -> str:
    if img_url.startswith('data:'):
        # secure temp filename
        filename = f"/tmp/{uuid.uuid4()}"
        with open(filename, 'wb') as f:
            f.write(DataURI(img_url).data)
            return filename
    else:
        response = requests.get(img_url)
        with open(filename, 'wb') as f:
            f.write(response.content)
            return filename

async def phi15_prompt_from_messages(messages: list[Message], img_tok = "<image>", img_end = ''): # </image>
    prompt = ''
    images = []

    for m in messages:
        if m.role == 'user':
            p = ''
            for c in m.content:
                if c.type == 'image_url':
                    images.extend([ await url_to_image(c.image_url.url) ])
                    p = img_tok + p + img_end
                if c.type == 'text':
                    p += f"{c.text}\n\n" # Question:
            prompt += p
        elif m.role == 'assistant':
            for c in m.content:
                if c.type == 'text':
                    prompt += f"Answer: {c.text}\n\n"

    prompt += "Answer:"

    return images, prompt

async def vicuna_prompt_from_messages(messages: list[Message], img_tok = "<image>\n"):
    prompt = ''
    images = []

    for m in messages:
        if m.role == 'user':
            text = ''
            has_image = False

            for c in m.content:
                if c.type == 'image_url':
                    images.extend([ await url_to_image(c.image_url.url) ])
                    has_image = True
                if c.type == 'text':
                    text = c.text
            
            img_tag = img_tok if has_image else ''
            prompt += f"USER: {img_tag}{text}\n"
        elif m.role == 'assistant':
            for c in m.content:
                if c.type == 'text':
                    prompt += f"ASSISTANT: {c.text}\n"

    prompt += "ASSISTANT:"

    return images, prompt

async def llama2_prompt_from_messages(messages: list[Message], img_tok = "<image>\n"):
    prompt = ''
    images = []

    for m in messages:
        if m.role == 'user':
            text = ''
            has_image = False

            for c in m.content:
                if c.type == 'image_url':
                    images.extend([ await url_to_image(c.image_url.url) ])
                    has_image = True
                if c.type == 'text':
                    text = c.text

            img_tag = img_tok if has_image else ''
            prompt += f"[INST] {img_tag}{text} [/INST]"
        elif m.role == 'assistant':
            for c in m.content:
                if c.type == 'text':
                    prompt += f" {c.text}"

    return images, prompt

async def chatml_prompt_from_messages(messages: list[Message], img_tok = "<image>\n"):
    prompt = ''
    images = []

    for m in messages:
        if m.role == 'user':
            text = ''
            has_image = False

            for c in m.content:
                if c.type == 'image_url':
                    images.extend([ await url_to_image(c.image_url.url) ])
                    has_image = True
                if c.type == 'text':
                    text = c.text

            img_tag = img_tok if has_image else ''
            prompt += f"<|im_start|>user\n{img_tag}{text}<|im_end|>"
        elif m.role == 'assistant':
            for c in m.content:
                if c.type == 'text':
                    prompt += f"<|im_start|>assistant\n{c.text}<|im_end|>"

    prompt += f"<|im_start|>assistant\n"

    return images, prompt

async def gemma_prompt_from_messages(messages: list[Message], img_tok = "<image>\n"):
    prompt = ''
    images = []

    for m in messages:
        if m.role == 'user':
            text = ''
            has_image = False

            for c in m.content:
                if c.type == 'image_url':
                    images.extend([ await url_to_image(c.image_url.url) ])
                    has_image = True
                if c.type == 'text':
                    text = c.text

            img_tag = img_tok if has_image else ''
            prompt += f"<|im_start|>user\n{img_tag}{text}<|im_end|>"
        elif m.role == 'assistant':
            for c in m.content:
                if c.type == 'text':
                    prompt += f"<|im_start|>assistant\n{c.text}<|im_end|>"

    prompt += f"<|im_start|>assistant\n"

    return images, prompt

async def prompt_from_messages(messages: list[Message], format: str) -> str:
    known_formats = {
        'phi15': phi15_prompt_from_messages,
        'vicuna': vicuna_prompt_from_messages,
        'llama2': llama2_prompt_from_messages,
        'mistral': llama2_prompt_from_messages, # simplicity
        'chatml': chatml_prompt_from_messages,
    }

    if format not in known_formats:
        raise ValueError(f"Unknown format: {format}")
    
    return await known_formats[format](messages)

def answer_from_response(response: str, format: str) -> str:
    """ parse out the model response from the prompt format """
    if format in ['llama2', 'mistral']:
        idx = response.rfind('[/INST]') + len('[/INST]') + 1 #+ len(images)
        return response[idx:]
    elif format == 'vicuna':
        idx = response.rfind('ASSISTANT:') + len('ASSISTANT:') + 1 #+ len(images)
        return response[idx:]
    elif format == 'chatml':
        idx = response.rfind('<|im_user|>assistant\n') + len('<|im_user|>assistant\n') + 1 #+ len(images)
        end_idx = response.rfind('<|im_end|>')
        return response[idx:end_idx]
    elif format == 'gemma':
        idx = response.rfind('<start_of_turn>model\n') + len('<start_of_turn>model\n') + 1 #+ len(images)
        end_idx = response.rfind('<end_of_turn>')
        return response[idx:end_idx]
    
def guess_model_format(model_name: str) -> str:
    model_id = model_name.lower()

    model_format_match_map = {
        'llama2': ['bakllava', '8x7b', 'mistral', 'mixtral'],
        'gemma': ['gemma', '2b'],
        'vicuna': ['vicuna', '13b'],
        'phi15': ['moondream1', 'moondream2'],
        'chatml': ['34b', 'yi-6b'],
    }
    for format, options in model_format_match_map.items():
        if any(x in model_id for x in options):
            return format

    return 'vicuna'

def guess_backend(model_name: str) -> str:
    model_id = model_name.lower()

    if 'llava' in model_id:
        if '1.5' in model_id:
            return 'llava'
        elif '1.6' in model_id:
            return 'llavanext'

    if 'qwen' in model_id:
        return 'qwen-vl'
    
    if 'moondream1' in model_id:
        return 'moondream1'
    if 'moondream2' in model_id:
        return 'moondream2'

    if 'monkey' in model_id:
        return 'monkey'
    
    if 'mini-gemini' in model_id:
        return 'minigemini'

    if 'deepseek' in model_id:
        return 'deepseek-vl'

    if 'minicpm-v' in model_id:
        return 'omnilmm3b'

    if 'omnilmm-12b' in model_id:
        return 'omnilmm12b'

    if 'xcomposer2-vl' in model_id:
        return 'xcomposer2-vl'
    elif 'xcomposer2' in model_id:
        return 'xcomposer2'