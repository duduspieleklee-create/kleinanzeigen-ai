#!/usr/bin/env python3
import time
from transformers import AutoModelForCausalLM
from peft import LoraConfig, get_peft_model
from transformers import AutoTokenizer

# Modell laden
model_name = 'qwen2.5:1.5b'
tokenizer = AutoTokenizer.from_pretrained(model_name)

# Modell mit bitsandbytes laden
model = AutoModelForCausalLM.from_pretrained(model_name, load_in_4bit=True)

# LoRA-Config
peft_config = LoraConfig(
    r=8, lora_alpha=16,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    lora_dropout=0.05,
    bias='none',
    task_type='CAUSAL_LM',
)

# LoRA-Modell laden
model_peft = get_peft_model(model, peft_config)

# Ladezeit messen
start_time = time.time()
model_peft = model_peft.to('cpu')
load_time = time.time() - start_time

print(f'LoRA-Modell {model_name} geladen in {load_time:.2f} Sekunden')
print(f'Trainable Parameters: {model_peft.print_trainable_parameters()}')

# Custom Model Endpoint mit Monetarisierung
print("\n--- Custom Model Endpoint mit Monetarisierung ---")
print("Pro-Plan nutzt LoRA-Modell für KI-Vorschläge")
print("Core-Plan nutzt Originalmodell")

# Beispiel: Vorschläge für Auto kaufen
print("Vorschläge für Auto kaufen:")
print("- Gebrauchtwagen (LoRA, Pro-Plan)")
print("- PKW kaufen (LoRA, Pro-Plan)")
print("- Auto gebraucht (LoRA, Pro-Plan)")
print("- Neues Auto finden (Original, Core-Plan)")