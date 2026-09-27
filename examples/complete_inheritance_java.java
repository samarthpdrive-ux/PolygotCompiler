class Person {
    String name = "Unknown";

    void describe() {
        print(name);
    }
}

class Student extends Person {
    void describe() {
        print("Student: " + name);
    }
}

public class complete_inheritance_java {
    public static void main(String[] args) {
        Student student = new Student();
        student.name = "Samarth";
        student.describe();
    }
}
