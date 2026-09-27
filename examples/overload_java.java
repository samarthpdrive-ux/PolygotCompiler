public class overload_java {
    public static void main(String[] args) {
        Formatter formatter = new Formatter();
        System.out.println(formatter.show(7));
        System.out.println(formatter.show("ready"));
    }
}

class Formatter {
    String show(int value) { return "number"; }
    String show(String value) { return "text"; }
}
