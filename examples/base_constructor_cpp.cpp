#include <iostream>

class Person {
    string name;
    Person(string value) { this.name = value; }
};

class Student : Person {
    Student(string value) : Person(value) { }
};

int main() {
    Student student = new Student("Samarth");
    cout << student.name << endl;
    return 0;
}
