import torch
from datasets import load_dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TrainingArguments
from trl import SFTTrainer

def run_fine_tuning():
    model_id = "meta-llama/Meta-Llama-3-8B"

    # 1. Load tokenizer and model with 4-bit quantization
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    model = AutoModelForCausalLM.from_pretrained(model_id, quantization_config=bnb_config, device_map="auto")
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token  # Set padding token

    # 2. Prepare model for k-bit training and configure LoRA
    model = prepare_model_for_kbit_training(model)
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM"
    )
    peft_model = get_peft_model(model, lora_config)
    peft_model.print_trainable_parameters()  # Shows the small percentage of trainable parameters

    # 3. Load and format dataset (assuming a pre-formatted dataset on the Hub)
    dataset = load_dataset("your-org/rail-debug-instructions", split="train")

    # 4. Set up TrainingArguments and SFTTrainer
    training_args = TrainingArguments(
        output_dir="./results",
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        num_train_epochs=3,
        logging_steps=10,
        fp16=True,  # Use mixed precision
    )

    trainer = SFTTrainer(
        model=peft_model,
        train_dataset=dataset,
        peft_config=lora_config,
        dataset_text_field="text",  # Assuming dataset has a 'text' field with formatted conversations
        max_seq_length=1024,
        tokenizer=tokenizer,
        args=training_args,
    )

    # 5. Start training
    trainer.train()

    # 6. Save the trained adapter
    trainer.save_model("./fine-tuned-adapter")