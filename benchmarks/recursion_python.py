def factorial(value):
    if value <= 1:
        return 1
    return value * factorial(value - 1)

result = factorial(8)
print(result)
