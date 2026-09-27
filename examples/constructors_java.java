class Student {
    String name;
    int age;

    Student(String studentName, int studentAge) {
        this.name = studentName;
        this.age = studentAge;
    }

    void display() {
        print(this.name);
        print(this.age);
    }
}

Student student = new Student("Samarth", 24);
student.display();
