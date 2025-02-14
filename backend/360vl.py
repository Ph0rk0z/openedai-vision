from transformers import AutoTokenizer, AutoModelForCausalLM

import transformers
import warnings
# disable some warnings
transformers.logging.set_verbosity_error()
warnings.filterwarnings('ignore')

from vision_qna import *
# "qihoo360/360VL-8B"
# "qihoo360/360VL-70B"

class VisionQnA(VisionQnABase):
    model_name: str = "360vl"
    format = "llama3"
    
    def __init__(self, model_id: str, device: str, device_map: str = 'auto', extra_params = {}, format = None):
        super().__init__(model_id, device, device_map, extra_params, format)

        if not format:
            self.format = guess_model_format(model_id)
        
        self.tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=self.params.get('trust_remote_code', False))
        self.model = AutoModelForCausalLM.from_pretrained(**self.params).eval()
        
        self.vision_tower = self.model.get_vision_tower()
        self.vision_tower.load_model()
        self.vision_tower.to(device=self.device, dtype=self.dtype)
        self.image_processor = self.vision_tower.image_processor
        self.tokenizer.pad_token = self.tokenizer.eos_token
        self.terminators = [
            self.tokenizer.convert_tokens_to_ids("<|eot_id|>",)
        ]
    
        print(f"Loaded on device: {self.model.device} with dtype: {self.model.dtype}")
    
    async def chat_with_images(self, request: ImageChatRequest) -> str:
        images, prompt = await llama3_prompt_from_messages(request.messages, img_tok = "<|reserved_special_token_44|>\n")

        default_system = "You are a multilingual, helpful, respectful and honest assistant who can respond in the same language, depending on the language of the question. Try to be as helpful as possible while still being safe. Your answer should not contain anything that is false, unhealthy, harmful, immoral, racist, sexist, toxic, dangerous, or illegal, and if the question relates to such content, please decline to answer. Make sure your answer is socially fair and positive. If a question doesn't make any sense, or is inconsistent with the facts, explain why instead of answering the wrong answer. If you don't know the answer to a question, don't share false information."

        input_ids = self.tokenizer.encode(prompt, return_tensors="pt")

        input_id_list = input_ids[0].tolist()
        input_id_list[input_id_list.index(128049)]=-200
        input_ids = torch.tensor(input_id_list, dtype=input_ids.dtype, device=input_ids.device).unsqueeze(0)

        image_tensor = self.model.process_images_slid_window(images[0], self.image_processor).unsqueeze(0)

        default_params = dict(
            do_sample=False,
            num_beams=1,
        )

        params = self.get_generation_params(request, default_params)

        output_ids = self.model.generate(
            input_ids=input_ids.to(device=self.device, non_blocking=True),
            images=image_tensor.to(dtype=self.dtype, device=self.device, non_blocking=True),
            eos_token_id=self.terminators,
            **params)

        outputs = self.tokenizer.batch_decode(output_ids[:, input_ids.shape[1]:], skip_special_tokens=True)[0]

        return outputs.strip()
