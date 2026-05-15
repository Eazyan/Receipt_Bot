import torch
import torchvision.transforms as T
from torchvision.transforms.functional import InterpolationMode
from transformers import AutoModel, AutoTokenizer
from PIL import Image

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)

def build_transform(input_size=448):
    return T.Compose([
        T.Lambda(lambda img: img.convert("RGB") if img.mode != "RGB" else img),
        T.Resize((input_size, input_size), interpolation=InterpolationMode.BICUBIC),
        T.ToTensor(),
        T.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])

def load_image(image_file, input_size=448):
    image = Image.open(image_file).convert("RGB")
    transform = build_transform(input_size)
    pixel_values = transform(image).unsqueeze(0)
    return pixel_values

MODEL_PATH = "baidu/Qianfan-OCR"

device = "mps" if torch.backends.mps.is_available() else "cpu"
dtype = torch.float16 if device in ("mps", "cuda") else torch.float32

model = AutoModel.from_pretrained(
    MODEL_PATH,
    trust_remote_code=True,
    dtype=dtype,
).eval().to(device)

tokenizer = AutoTokenizer.from_pretrained(
    MODEL_PATH,
    trust_remote_code=True
)

image_path = "/Users/eazyan/Documents/ocr/test2.jpg"
pixel_values = load_image(image_path).to(device=device, dtype=dtype)

prompt = "Parse this document to Markdown."

with torch.no_grad():
    response = model.chat(
        tokenizer,
        pixel_values=pixel_values,
        question=prompt,
        generation_config={"max_new_tokens": 4096}
    )

print(response)