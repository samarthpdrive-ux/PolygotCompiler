class Student {
    string name;
    int age;

    Student(string studentName, int studentAge) {
        this.name = studentName;
        this.age = studentAge;
    }

    void display() {
        print(this.name);
        print(this.age);
    }
};

Student student = new Student("Samarth", 24);
student.display();
