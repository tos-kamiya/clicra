from typing import Callable, Dict, Iterable, Iterator, List, Optional, Tuple
from typing import IO, TextIO

import argparse
import re
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

_version = pkg_resources.get_distribution("clicra").version

DEFAULT_LLM = "llama3"
LARGER_LLM = "llama3:70b"
DEFAULT_OUTPUT_MAX_CHARS = 2000

PROMPTINGS : Dict[str, str] = {
    "sbs": """(Let’s work this out in a step by step way to be sure we have the right answer.

""",  # ref: https://arxiv.org/pdf/2211.01910
    "tot": """magine three different experts are answering this question. All experts will write down 1 step of their thinking, then share it with the group.
Then all experts will go on to the next step, etc. If any expert realises they're wrong at any point then they leave.

""",  # ref: https://github.com/dave1010/tree-of-thought-prompting
}


def clip_text(text: str, max_chars: int) -> str:
    if len(text) == 0:
        return "\n"

    snip_str = " ...(snip)... "

    newline_pos = text.find("\n")
    if newline_pos < 0 or newline_pos > max_chars:
        return text[:max_chars] + snip_str + "\n"

    while newline_pos >= 0:
        next_newline_pos = text.find("\n", newline_pos + 1)
        if next_newline_pos < 0 or next_newline_pos > max_chars:
            return text[: newline_pos + 1] + snip_str + "\n"
        newline_pos = next_newline_pos

    if not text.endswith("\n"):
        text = text + "\n"
    return text


def stream_reader(stream: IO, output: TextIO, output_list: List[str]) -> None:
    for line in iter(stream.readline, b""):
        line = line.decode("utf-8")
        output_list.append(line)


def stream_reader_thru(stream: IO, output: TextIO, output_list: List[str]) -> None:
    for line in iter(stream.readline, b""):
        line = line.decode("utf-8")
        output_list.append(line)
        print(line, file=output, end="")


def do_run_and_capture(code: str, thru_output=True) -> Tuple[int, str, str]:
    """Run the code and capture the standard out and standard error."""

    lines = []
    for L in code.split("\n"):
        if L.startswith("$ "):
            L = L[2:]
        lines.append(L)

    process = subprocess.Popen(["bash", "-c", "\n".join(lines)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    stdout_list = []
    stderr_list = []

    sr = stream_reader_thru if thru_output else stream_reader

    stdout_thread = threading.Thread(target=sr, args=(process.stdout, sys.stdout, stdout_list))
    stderr_thread = threading.Thread(target=sr, args=(process.stderr, sys.stderr, stderr_list))

    stdout_thread.start()
    stderr_thread.start()

    process.wait()

    stdout_thread.join()
    stderr_thread.join()

    stdout = "".join(stdout_list).rstrip()
    stderr = "".join(stderr_list).rstrip()

    return process.returncode, stdout, stderr


def highlight_and_extract_command(line_iter: Iterable[str], print_func: Callable[[str], None]) -> Optional[str]:
    """Extract the first code block enclosed by "```" and add highlights to the text."""

    in_code_block = False
    code_block = []
    pat_code_block_start = re.compile("^```")
    pat_code_block_end = re.compile("^```")

    for line in line_iter:
        line = line.rstrip()
        if in_code_block:
            if pat_code_block_start.match(line):
                print_func(line)
                in_code_block = False
            else:
                code_block.append(line)
                print_func(colored(line, "green", attrs=["bold"]))
        else:
            print_func(line)
            if not code_block and pat_code_block_end.match(line):
                in_code_block = True

    return "\n".join(code_block) if code_block else None


def format_command_generation_prompt(
    task: str, context: Optional[str], generate_script: bool = False, prompting: Optional[str] = None
) -> str:
    p = PROMPTINGS.get(prompting, "") if prompting is not None else ""
    if generate_script:
        p += f"Please provide a script to accomplish the following task."
    else:
        p += f"Please provide a command line to accomplish the following task."
    if task:
        p += f"\n## TASK\n{task}\n"
    if context:
        p += f"\n## CONTEXT\n{context}\n"
    return p


def format_analysis_prompt(
    code: str, task: Optional[str], context: Optional[str], stdout: Optional[str], stderr: Optional[str]
) -> str:
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


def build_reference_context(command: str, max_chars: int) -> str:
    context = None
    exit_code, stdout, stderr = do_run_and_capture(command, thru_output=False)
    r = ["```", f"$ {command}"]
    if stdout:
        r.append(clip_text(stdout, max_chars))
    if stderr:
        r.append(clip_text(stderr, max_chars))
    if exit_code != 0:
        r.append(f"EXIT CODE: {exit_code}")
    r.append("```")
    context = "\n".join(r)
    return context


def line_it(stream) -> Iterable[str]:
    buf = ""
    for chunk in stream:
        buf += chunk['message']['content']
        i = buf.find("\n")
        while i >= 0:
            yield buf[:i]
            buf = buf[i + 1:]
            i = buf.find("\n")
    if buf:
        if buf.endswith("\n"):
            buf = buf[:-1]
        yield buf


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate command line from task description")
    parser.add_argument("task", nargs="*", help="description of the task to perform")
    g = parser.add_mutually_exclusive_group()
    g.add_argument("-r", "--run", action="store_true", help="generate command, run it, and then analyze the result.")
    g.add_argument(
        "-s",
        "--script",
        action="store_true",
        help="ask to generate a script (instead of a command line).",
    )
    g.add_argument(
        "-p",
        "--prompt",
        choices=["tot", "sbs"],
        help="ask for a prompt to describe the solution (**experimental feature**). `tot` for Tree-of-Thought. `sbs` for Step-by-Step.",
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
        "-M",
        "--max-chars",
        type=int,
        default=DEFAULT_OUTPUT_MAX_CHARS,
        help="max characters of command execution results.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--version", action="version", version=f"%(prog)s {_version}")
    args = parser.parse_args()

    if not args.task:
        exit("Error: no task is given. Option `-h` for help.")
    task = " ".join(args.task)

    if args.verbose:
        print(colored(f"Model: {args.model}", attrs=["dark"]) + "\n", file=sys.stderr)

    context = build_reference_context(args.refer, args.max_chars) if args.refer else None

    def chat_stream_line_iter(p: str) -> Iterator[str]:
        stream = ollama.chat(
            model=args.model,
            messages=[{"role": "user", "content": p}],
            stream=True,
        )
        return line_it(stream)

    p = format_command_generation_prompt(
        task,
        context,
        generate_script=args.script,
        prompting=args.prompt,
    )
    if args.verbose:
        for L in p.split("\n"):
            print(colored(L, attrs=["dark"]), file=sys.stderr)

    if args.prompt:
        for L in chat_stream_line_iter(p):
            print(L)
        command = None
    else:
        command = highlight_and_extract_command(chat_stream_line_iter(p), print)

    if command:
        if args.run:
            ht_run = colored(f"-- RUN", "yellow", attrs=["bold"])
            print(f"\n{ht_run}: {command}\n")
            exit_code, stdout, stderr = do_run_and_capture(command)
            if exit_code != 0:
                print("\n" + colored("-- DEBUG", "yellow", attrs=["bold"]) + "\n")
                p = format_analysis_prompt(
                    command, task, context, clip_text(stdout, args.max_chars), clip_text(stderr, args.max_chars)
                )
                if args.verbose:
                    for L in p.split("\n"):
                        print(colored(L, attrs=["dark"]), file=sys.stderr)
                for L in chat_stream_line_iter(p):
                    print(L)
            exit(exit_code)
        else:
            pyperclip.copy(command)
            ht_copied = colored(f"-- COPIED THE HIGHLIGHTED CODE TO CLIPBOARD", "yellow", attrs=["bold"])
            print(f"\n{ht_copied}\n")


if __name__ == "__main__":
    main()
