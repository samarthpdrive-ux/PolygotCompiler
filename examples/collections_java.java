
public class collections_java {
    public static void main(String[] args) {
        ArrayList<Integer> scores = new ArrayList();
        scores.add(82);
        scores.add(91);

        HashMap<String, Integer> marks = new HashMap();
        marks.put("Samarth", scores.get(1));

        System.out.println(marks.get("Samarth"));
    }
}
