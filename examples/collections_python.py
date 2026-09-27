scores = {"Samarth": 82, "Ada": 91}
scores["Samarth"] = scores["Samarth"] + 3

names = scores.keys()
unique_marks = {scores["Samarth"], scores["Ada"]}
unique_marks.add(100)

print(names)
print(len(unique_marks))
