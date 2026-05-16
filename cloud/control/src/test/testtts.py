from transformers import VitsModel, AutoTokenizer
import torch
import scipy

model = VitsModel.from_pretrained("facebook/mms-tts-hun")
tokenizer = AutoTokenizer.from_pretrained("facebook/mms-tts-hun")

text = "Mikrofonpróba, 1-2-3. Hello hello, ez it a dogirádió!"
inputs = tokenizer(text, return_tensors="pt")

with torch.no_grad():
    output = model(**inputs).waveform.squeeze().numpy()
    scipy.io.wavfile.write("techno.wav", rate=model.config.sampling_rate, data=output)