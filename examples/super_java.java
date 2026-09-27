public class super_java {
    public static void main(String[] args) {
        Student student = new Student("Samarth", 4);
        System.out.println(student.name);
        System.out.println(student.year);
    }
}

class Person {
    String name;

    Person(String value) {
        this.name = value;
    }
}

class Student extends Person {
    int year;

    Student(String value, int level) {
        super(value);
        this.year = level;
    }
}
