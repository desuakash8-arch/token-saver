import argparse
import json
from pathlib import Path
import sys

from .analyzer import analyze
from .catalog import catalog
from .schemas import AnalysisRequest
from .tokenizer import encoding


def main():
    parser = argparse.ArgumentParser(prog="token-saver", description="Know your tokens before you send.")
    commands = parser.add_subparsers(dest="command")
    serve = commands.add_parser("serve", help="Start the local web application")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    commands.add_parser("models", help="List model presets")
    commands.add_parser("warmup", help="Download and cache tokenizer vocabularies once")
    count = commands.add_parser("analyze", help="Analyze text without running the web server")
    group = count.add_mutually_exclusive_group(required=True)
    group.add_argument("--text")
    group.add_argument("--file", type=Path)
    count.add_argument("--model", default="gpt-5.4-mini")
    count.add_argument("--output", type=int, default=512, help="Visible response budget")
    count.add_argument("--reasoning", type=int, default=0)
    count.add_argument("--calls", type=int, default=1000)
    count.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        if args.command in {None, "serve"}:
            import uvicorn
            uvicorn.run("token_saver.app:app", host=getattr(args, "host", "127.0.0.1"), port=getattr(args, "port", 8000), reload=getattr(args, "reload", False))
        elif args.command == "models":
            for model in catalog()["models"]:
                print(f"{model['id']:<24} {model['provider_name']:<16} ${model['input_price']} in / ${model['output_price']} out per 1M")
        elif args.command == "warmup":
            for name in ("o200k_base", "cl100k_base"):
                encoding(name)
                print(f"Cached {name}")
        else:
            text = args.file.read_text(encoding="utf-8-sig") if args.file else args.text
            request = AnalysisRequest(prompt=text, model_id=args.model, output_low=args.output // 2, output_expected=args.output, output_high=args.output * 2, reasoning_tokens=args.reasoning, calls=args.calls)
            result = analyze(request, preview=False)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"Token Saver | {result['model']['name']}")
                print(f"Input: {result['counting']['input_tokens']:,} tokens ({result['counting']['method']})")
                print(f"Expected scenario: {result['scenarios']['expected']['total_tokens']:,} total tokens")
                print(f"Estimated cost: ${result['scenarios']['expected']['total_usd']:.6f} per call")
                print(f"{args.calls:,} calls: ${result['volume']['total_usd']:.4f}")
                print("Output is a budget, not a prediction; see --json for assumptions.")
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
