int age = 0;

try {
    age = 10 / 0;
} catch {
    print("Invalid calculation");
    age = 18;
}

print(age);
