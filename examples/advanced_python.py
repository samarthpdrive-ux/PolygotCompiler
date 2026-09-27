import math

values = [value * 2 for value in [1, 2, 3, 4]]
point = (values[0], values[3])

with open("advanced_result.txt", "w") as file:
    file.write(str(math.sqrt(81)))

print(point)
