from transformers import LlamaTokenizer, AutoModelForCausalLM

from vision_qna import *

# THUDM/cogvlm-chat-hf
# THUDM/cogagent-chat-hf
import transformers
transformers.logging.set_verbosity_error()

class VisionQnA(VisionQnABase):
    model_name: str = "cogvlm"
    format: str = 'llama2'
    
    def __init__(self, model_id: str, device: str, device_map: str = 'auto', extra_params = {}, format = None):
        super().__init__(model_id, device, device_map, extra_params, format)

        self.tokenizer = LlamaTokenizer.from_pretrained("lmsys/vicuna-7b-v1.5")
        self.model = AutoModelForCausalLM.from_pretrained(**self.params).eval()
    
        print(f"Loaded on device: {self.model.device} with dtype: {self.model.dtype}")
    
    async def chat_with_images(self, request: ImageChatRequest) -> str:
        
        query, history, images, system_message = await prompt_history_images_system_from_messages(
            request.messages, img_tok='', url_handler=url_to_image)

        input_by_model = self.model.build_conversation_input_ids(self.tokenizer, query=query, history=history, images=images)
        
        inputs = {
            'input_ids': input_by_model['input_ids'].unsqueeze(0).to(self.model.device),
            'token_type_ids': input_by_model['token_type_ids'].unsqueeze(0).to(self.model.device),
            'attention_mask': input_by_model['attention_mask'].unsqueeze(0).to(self.model.device),
            'images': [[input_by_model['images'][0].to(self.model.device).to(self.model.dtype)]],
        }
        if 'cross_images' in input_by_model and input_by_model['cross_images']:
            inputs['cross_images'] = [[input_by_model['cross_images'][0].to(self.model.device).to(self.model.dtype)]]

        params = self.get_generation_params(request)
        del params['top_k']
        response = self.model.generate(**inputs, **params)
        answer = self.tokenizer.decode(response[0][inputs['input_ids'].size(1):].cpu(), skip_special_tokens=True).strip()

        return answer
