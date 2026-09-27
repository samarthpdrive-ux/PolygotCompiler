#include <iostream>

class Person {
    string name = "Unknown";
    void describe() {
        print(name);
    }
};

class Student : Person {
    void describe() {
        print("Student: " + name);
    }
};

int main() {
    Student student = new Student();
    student.name = "Samarth";
    student.describe();
    return 0;
}
