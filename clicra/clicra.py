from typing import Tuple, List, Optional
from typing import IO, TextIO

import argparse
import subprocess
import sys
import threading

import pyperclip
from termcolor import colored

try:
    import ollama
except ImportError:
    exit("Install `ollama-python` by following the instruction on: https://github.com/ollama/ollama-python")


import pkg_resources
_version = pkg_resources.get_distribution('clicra').version

DEFAULT_LLM = "llama3"


def stream_reader(
    stream: IO, output: TextIO, output_list: List[str]
) -> None:
    for line in iter(stream.readline, b""):
        line = line.decode("utf-8")
        output_list.append(line)


def stream_reader_thru(
    stream: IO, output: TextIO, output_list: List[str]
) -> None:
    for line in iter(stream.readline, b""):
        line = line.decode("utf-8")
        output_list.append(line)
        print(line, file=output, end="")


def do_run_and_capture(code: str, thru_output=True) -> Tuple[int, str, str]:
    """Run the code and capture the standard out and standard error."""

    lines = []
    for L in code.split('\n'):
        if L.startswith("$ "):
            L = L[2:]
        lines.append(L)

    process = subprocess.Popen(
        ["bash", "-c", "\n".join(lines)], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    stdout_list = []
    stderr_list = []

    sr = stream_reader_thru if thru_output else stream_reader

    stdout_thread = threading.Thread(
        target=sr, args=(process.stdout, sys.stdout, stdout_list)
    )
    stderr_thread = threading.Thread(
        target=sr, args=(process.stderr, sys.stderr, stderr_list)
    )

    stdout_thread.start()
    stderr_thread.start()

    process.wait()

    stdout_thread.join()
    stderr_thread.join()

    stdout = "".join(stdout_list).rstrip()
    stderr = "".join(stderr_list).rstrip()

    return process.returncode, stdout, stderr


def highlight_and_extract_code(text: str) -> Tuple[str, str]:
    """Extract the first code block enclosed by "```" and add highlights to the text."""

    lines = text.splitlines()
    in_code_block = False
    highlighted_lines = []
    code_block = []
    for line in lines:
        if in_code_block:
            if line.startswith("```"):
                highlighted_lines.append(line)
                in_code_block = False
            else:
                code_block.append(line)
                highlighted_lines.append(colored(line, "green", attrs=["bold"]))
        else:
            highlighted_lines.append(line)
            if not code_block and line.startswith("```"):
                in_code_block = True
    return "\n".join(highlighted_lines), "\n".join(code_block)


def format_command_generation_prompt(task: str, context: Optional[str]) -> str:
    p = f"Please provide the command line to accomplish the following task."
    if task:
        p += f"\n## TASK\n{task}\n"
    if context:
        p += f"\n## CONTEXT\n{context}\n"
    return p


def format_analysis_prompt(code: str, task: Optional[str], context: Optional[str], stdout: Optional[str], stderr: Optional[str]) -> str:
    p = f"Analyze the result of the command.\n"
    if task:
        p += f"\n## TASK\n{task}\n"
    if context:
        p += f"\n## CONTEXT\n{context}\n"
    p += f"\n## COMMAND\n```\n{code}\n```\n"
    if stdout:
        p += f"\n## STDOUT\n{stdout}\n"
    if stderr:
        p += f"\n## STDERR\n{stderr}\n"

    return p


def build_reference_context(command: str) -> str:
    context = None
    exit_code, stdout, stderr = do_run_and_capture(command, thru_output=False)
    r = ["```", f"$ {command}"]
    if stdout:
        r.append(stdout)
    if stderr:
        r.append(stderr)
    if exit_code != 0:
        r.append(f"EXIT CODE: {exit_code}")
    r.append("```")
    context = "\n".join(r)
    return context


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate command line from task description"
    )
    parser.add_argument("task", nargs="*", help="description of the task to perform")
    parser.add_argument(
        "-r", "--run", action="store_true", help="generate command, run it, and then analyze the result."
    )
    parser.add_argument(
        "-f",
        "--refer",
        help="provide a command to execute and use its output as additional context.",
    )
    parser.add_argument(
        "-m",
        "--model",
        default=DEFAULT_LLM,
        help="LLM name to use.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true"
    )
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {_version}")
    args = parser.parse_args()

    if not args.task:
        exit("Error: no task is given. Option `-h` for help.")
    task = " ".join(args.task)

    def chat(prompt: str) -> str:
        response = ollama.chat(
            model=args.model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response["message"]["content"]

    context = build_reference_context(args.refer) if args.refer else None

    p = format_command_generation_prompt(task, context)
    if args.verbose:
        for L in p.split("\n"):
            print(colored(L, attrs=["dark"]), file=sys.stderr)
    command = chat(p)

    highlighted_text, code = highlight_and_extract_code(command)
    print(highlighted_text)

    if code:
        if args.run:
            ht_run = colored(f"-- RUN", "yellow", attrs=["bold"])
            print(f"\n{ht_run}: {code}\n")
            exit_code, stdout, stderr = do_run_and_capture(code)
            if exit_code != 0:
                print("\n" + colored("-- DEBUG", "yellow", attrs=["bold"]) + "\n")
                p = format_analysis_prompt(code, task, context, stdout, stderr)
                if args.verbose:
                    for L in p.split("\n"):
                        print(colored(L, attrs=["dark"]), file=sys.stderr)
                analysis = chat(p)
                print(analysis)
            exit(exit_code)
        else:
            pyperclip.copy(code)
            ht_copied = colored(f"-- COPIED THE HIGHLIGHTED CODE TO CLIPBOARD", "yellow", attrs=["bold"])
            print(f"\n{ht_copied}\n")


if __name__ == "__main__":
    main()
