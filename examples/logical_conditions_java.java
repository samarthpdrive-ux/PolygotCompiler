int age = 20;
int marks = 72;
boolean registered = true;

if ((age >= 18 && marks >= 50) && registered) {
    print("Eligible");
} else {
    print("Not eligible");
}

if (!(marks < 50) || age < 18) {
    print("Condition checked");
}
