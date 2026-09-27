age = 20
marks = 72
registered = True

if (age >= 18 and marks >= 50) and registered:
    print("Eligible")
else:
    print("Not eligible")

if not (marks < 50) or age < 18:
    print("Condition checked")
