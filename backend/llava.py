from transformers import LlavaProcessor, LlavaForConditionalGeneration
from vision_qna import *

#
# llava-hf/bakLlava-v1-hf # llama2
# llava-hf/llava-1.5-7b-hf # vicuna
# llava-hf/llava-1.5-13b-hf # vicuna

class VisionQnA(VisionQnABase):
    model_name: str = "llava"
    format: str = 'vicuna'
    
    def __init__(self, model_id: str, device: str, extra_params = {}, format = None):
        super().__init__(model_id, device, extra_params, format)

        if not format:
            self.format = guess_model_format(model_id)

        self.processor = LlavaProcessor.from_pretrained(model_id)
        self.model = LlavaForConditionalGeneration.from_pretrained(**self.params).eval()

        print(f"Loaded on device: {self.model.device} with dtype: {self.model.dtype}")

    async def chat_with_images(self, messages: list[Message], max_tokens: int) -> str:
                               
        images, prompt = await prompt_from_messages(messages, self.format)
        inputs = self.processor(prompt, images, return_tensors="pt").to(self.device)

        output = self.model.generate(**inputs, max_new_tokens=max_tokens)
        response = self.processor.decode(output[0], skip_special_tokens=True)
        
        return answer_from_response(response, self.format)
