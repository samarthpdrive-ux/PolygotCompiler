# Inspect this file with --disassemble, then compare --profile with and
# without --optimize. The constant expression becomes one PUSH instruction.

def score():
    return (2 + 3) * 4

result = score()
print(result)
