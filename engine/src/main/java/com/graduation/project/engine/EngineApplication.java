package com.graduation.project.engine;

import com.graduation.project.engine.models.TestDoc;
import com.graduation.project.engine.repository.TestDocRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

import java.util.List;

@SpringBootApplication
@EnableMongoRepositories
public class EngineApplication implements CommandLineRunner {


    @Autowired
    TestDocRepository repository;

    public static void main(String[] args) {
        SpringApplication.run(EngineApplication.class, args);
    }

    @Override
    public void run(String... args) throws Exception {
        createGroceryItems();
        showAllGroceryItems();
    }

    //CREATE
    void createGroceryItems() {
        System.out.println("Data creation started...");
        repository.save(new TestDoc("Whole Wheat Biscuit", "Whole Wheat Biscuit", 5, "snacks"));
        repository.save(new TestDoc("Kodo Millet", "XYZ Kodo Millet healthy", 2, "millets"));
        repository.save(new TestDoc("Dried Red Chilli", "Dried Whole Red Chilli", 2, "spices"));
        repository.save(new TestDoc("Pearl Millet", "Healthy Pearl Millet", 1, "millets"));
        repository.save(new TestDoc("Cheese Crackers", "Bonny Cheese Crackers Plain", 6, "snacks"));
        System.out.println("Data creation complete...");
    }

    // READ
    // 1. Show all the data
    public void showAllGroceryItems() {

        repository.findAll().forEach(item -> System.out.println(getItemDetails(item)));
    }

    // 2. Get item by name
    public void getGroceryItemByName(String name) {
        System.out.println("Getting item by name: " + name);
        TestDoc item = repository.findItemByName(name);
        System.out.println(getItemDetails(item));
    }

    // 3. Get name and quantity of a all items of a particular category
    public void getItemsByCategory(String category) {
        System.out.println("Getting items for the category " + category);
        List<TestDoc> list = repository.findAll(category);

        list.forEach(item -> System.out.println("Name: " + item.getName() + ", Quantity: " + item.getQuantity()));
    }

    // 4. Get count of documents in the collection
    public void findCountOfGroceryItems() {
        long count = repository.count();
        System.out.println("Number of documents in the collection: " + count);
    }

    // Print details in readable form

    public String getItemDetails(TestDoc item) {

        System.out.println(
                "Item Name: " + item.getName() +
                        ", \nQuantity: " + item.getQuantity() +
                        ", \nItem Category: " + item.getCategory()
        );

        return "";
    }
}
