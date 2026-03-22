import argparse
import os
import time

import config
import utils


def build_joke_prompt(topic=None):
    if topic:
        return (
            f"Tell me one short, funny joke about {topic}. "
            "Return only the joke text."
        )

    return "Tell me one short, funny joke. Return only the joke text."


def main():
    parser = argparse.ArgumentParser(description='Test prompt call using project config settings')
    parser.add_argument('--topic', default='', help='Optional joke topic')
    parser.add_argument('--prompt', default='', help='Custom prompt text (overrides joke/topic prompt)')
    parser.add_argument('--image', '--iamga', dest='image', default='', help='Optional image file path to attach to the prompt')
    parser.add_argument('--stream', action='store_true', help='Use streaming response mode')
    parser.add_argument('--tts', action='store_true', help='Speak the model response using configured TTS')
    args = parser.parse_args()

    # Read configuration through config.py singletons.
    cfg = config.get_config_data()
    model = config.get_general_model()
    prompt_lang = config.get_prompt_language()

    print('Loaded config settings:')
    print(f"  openai.api_base: {cfg.get('openai', {}).get('api_base')}")
    print(f"  openai.keep_alive: {cfg.get('openai', {}).get('keep_alive')}")
    print(f"  openai.max_output_tokens: {cfg.get('openai', {}).get('max_output_tokens')}")
    print(f"  model.general: {model}")
    print(f"  language.prompt: {prompt_lang}")

    prompt_text = args.prompt.strip() or build_joke_prompt(args.topic.strip() or None)
    images = None
    if args.image:
        image_path = os.path.expanduser(args.image.strip())
        images = [image_path]

        if not os.path.exists(image_path):
            print(f"Warning: image file does not exist: {image_path}")

    print(f"\nSending prompt: {prompt_text}\n")
    if images:
        print(f"Attaching image: {images[0]}\n")

    # Route through utils.prompt so all current request settings/debug apply.
    response = utils.prompt(prompt_text, images=images, stream=args.stream)

    print('Model response:')
    print(response)

    if args.tts:
        if response and str(response).strip():
            wav, duration = utils.tts_wav(str(response).strip())
            utils.play_wav(wav)
            time.sleep(duration)
        else:
            print('TTS skipped: empty response.')


if __name__ == '__main__':
    main()
