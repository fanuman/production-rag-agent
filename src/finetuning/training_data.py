import json
import os

TRAINING_EXAMPLES = [
    {"messages": [
        {"role": "system", "content": "You are the TrailPeak Outdoors assistant."},
        {"role": "user", "content": "What tent works for winter camping?"},
        {"role": "assistant", "content": "We don't currently carry a tent rated for winter/4-season conditions - our AlpinePeak 2-Person Tent is built for 3-season use only and isn't rated for sustained heavy snow load. For serious winter camping, you'd want a dedicated 4-season tent from another retailer. In the meantime, I can help you find cold-weather sleeping bags or insulation layers we do carry, if that's useful."}
    ]},
    {"messages": [
        {"role": "system", "content": "You are the TrailPeak Outdoors assistant."},
        {"role": "user", "content": "Do you have any climbing harnesses?"},
        {"role": "assistant", "content": "We don't currently carry climbing harnesses or other technical climbing gear - our catalog is focused on hiking and backpacking equipment. I'd recommend checking a dedicated climbing retailer for that. Is there anything else in hiking or backpacking gear I can help with?"}
    ]},
    {"messages": [
        {"role": "system", "content": "You are the TrailPeak Outdoors assistant."},
        {"role": "user", "content": "What kayaks do you sell?"},
        {"role": "assistant", "content": "We don't carry kayaks or other paddling gear - TrailPeak focuses on hiking, backpacking, and camping equipment. A dedicated watersports retailer would be a better fit for that. Happy to help with anything hiking or camping-related instead."}
    ]},
    {"messages": [
        {"role": "system", "content": "You are the TrailPeak Outdoors assistant."},
        {"role": "user", "content": "Do you have ski or snowboard equipment?"},
        {"role": "assistant", "content": "We don't carry ski or snowboard gear - our catalog is centered on hiking and backpacking equipment rather than snow sports. For winter hiking or snowshoeing-adjacent needs, though, I can check what cold-weather clothing and footwear we do have, if that would help."}
    ]},
    {"messages": [
        {"role": "system", "content": "You are the TrailPeak Outdoors assistant."},
        {"role": "user", "content": "I need road running shoes for a marathon."},
        {"role": "assistant", "content": "We don't carry road running shoes - our footwear lineup is built for trail hiking and backpacking, not road running. A running specialty store would serve you better for marathon training shoes. If you're ever looking for trail or hiking footwear, I'm happy to help with that instead."}
    ]},
    {"messages": [
        {"role": "system", "content": "You are the TrailPeak Outdoors assistant."},
        {"role": "user", "content": "Do you sell fishing rods or tackle?"},
        {"role": "assistant", "content": "We don't carry fishing gear - TrailPeak's catalog is focused on hiking, backpacking, and camping equipment. A dedicated fishing or outdoor sporting goods store would have what you need there. Let me know if there's any camping or hiking gear I can help with."}
    ]},
    {"messages": [
        {"role": "system", "content": "You are the TrailPeak Outdoors assistant."},
        {"role": "user", "content": "Do you have an ice axe for mountaineering?"},
        {"role": "assistant", "content": "We don't currently carry ice axes or other technical mountaineering hardware - our gear is built for 3-season hiking and backpacking rather than technical alpine routes. For serious mountaineering equipment, a specialized alpine retailer would be a better source. Happy to help with backpacking or camping gear in the meantime."}
    ]},
    {"messages": [
        {"role": "system", "content": "You are the TrailPeak Outdoors assistant."},
        {"role": "user", "content": "What swimwear do you carry?"},
        {"role": "assistant", "content": "We don't carry swimwear - TrailPeak's focus is hiking, backpacking, and camping equipment rather than water or beach gear. Let me know if there's any trail or camping gear I can help you find instead."}
    ]},
    {"messages": [
        {"role": "system", "content": "You are the TrailPeak Outdoors assistant."},
        {"role": "user", "content": "Do you sell road bikes or cycling gear?"},
        {"role": "assistant", "content": "We don't carry bikes or cycling equipment - our catalog is centered on hiking and backpacking gear rather than cycling. A bike shop would be the better resource for that. I'm happy to help with anything trail or camping-related instead."}
    ]},
    {"messages": [
        {"role": "system", "content": "You are the TrailPeak Outdoors assistant."},
        {"role": "user", "content": "Do you have a 4-person family camping tent?"},
        {"role": "assistant", "content": "Our current tent lineup is the AlpinePeak 2-Person Tent, so we don't have a larger 4-person option right now. If two smaller tents or gear for a group camping setup could work for your trip, I'm happy to help figure that out - or point you toward what a 2-person tent could still work for."}
    ]},
    {"messages": [
        {"role": "system", "content": "You are the TrailPeak Outdoors assistant."},
        {"role": "user", "content": "Do you carry drones for outdoor photography?"},
        {"role": "assistant", "content": "We don't carry drones or camera equipment - TrailPeak's catalog is focused on hiking and backpacking gear rather than electronics or photography equipment. A dedicated electronics retailer would have what you're looking for there."}
    ]},
    {"messages": [
        {"role": "system", "content": "You are the TrailPeak Outdoors assistant."},
        {"role": "user", "content": "What hunting gear do you sell?"},
        {"role": "assistant", "content": "We don't carry hunting gear - our focus is hiking, backpacking, and general camping equipment rather than hunting-specific products. A specialty outdoor or hunting retailer would be better suited for that. Let me know if there's hiking or camping gear I can help with."}
    ]},
]


def build_dataset(output_path="src/finetuning/datasets/no_match_pattern.jsonl"):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        for example in TRAINING_EXAMPLES:
            f.write(json.dumps(example) + "\n")
    print(f"Wrote {len(TRAINING_EXAMPLES)} examples to {output_path}")


if __name__ == "__main__":
    build_dataset()