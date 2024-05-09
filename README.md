# clicra, Command-line Crafter

A command-line tool named `clicra` leverages LLM to generate and analyze command lines based on user-provided tasks and context.

## Installation

Install:

```sh
pipx install clicra
```

Uninstall:

```sh
pipx uninstall clicra
```

## Usage

```sh
clicra [options] task ...
```

* `task`: Description of the task to perform.

### Options

* `-r/--run`: Generate command, run it, and analyze the result.
* `-f/--refer`: Provide a command to execute and use its output as additional context.
* `-m/--model`: LLM name to use (default: llama3).

Example

```sh
clicra "Find TODOs in source files" -f "ls"
```
