# clicra: Command Line Crafter

`clicra` is a command-line tool that utilizes local large language models (LLMs) to generate and analyze command lines based on tasks provided by users.

## Installation

`clicra` requires `Ollama` to be installed beforehand. Please follow the instructions on the official Ollama website.

1. Visit Ollama at [https://ollama.com/](https://ollama.com/).
2. Download the installer from the Download section.
3. Execute the downloaded installer.

After installing Ollama, you can install `clicra`. Use `pipx`, a package manager for Python applications:

```sh
pipx install clicra
```

To uninstall:

```sh
pipx uninstall clicra
```

## Usage

To run `clicra`, provide a description of the task you want to execute as a command-line argument:

```sh
clicra [options] <task>
```

### Options

- `-m, --model`: Specifies the LLM to use (default is `llama3`).
- `-r, --run`: Generates and executes the command immediately without confirmation, and analyzes the outcome if there are errors (non-zero exit code).
- `-s, --script`: Generates a script instead of a command.
- `-f, --refer`: Executes a specified command and uses its output as additional context to improve the accuracy and relevance of task command generation.
- `-M, --max-chars`: Specifies the maximum number of characters to include from the referred command's output in the prompt (default is `2000`).

### Examples

To find source files containing TODO comments, you can provide the output of `ls` as context. This allows `clicra` to recognize the directory structure and file types:

```sh
clicra "Find TODOs in source files" -f "ls"
```

## Screenshots

![](imgs/screenshot2.png)
