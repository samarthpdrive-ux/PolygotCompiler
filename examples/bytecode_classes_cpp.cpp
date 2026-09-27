#include <iostream>

class Person {
    string name;

    Person(string value) {
        this.name = value;
    }
};

class Student : Person {
    int score;

    Student(string value, int initialScore) : Person(value) {
        this.score = initialScore;
    }

    int increase(int points) {
        score += points;
        return score;
    }

    void show() {
        print(name);
        print(score);
    }
};

int main() {
    Student student = new Student("Samarth", 80);
    student.increase(15);
    student.show();
    return 0;
}
