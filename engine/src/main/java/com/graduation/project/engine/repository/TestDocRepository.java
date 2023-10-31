package com.graduation.project.engine.repository;

import com.graduation.project.engine.models.TestDoc;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

import java.util.List;

public interface TestDocRepository extends MongoRepository<TestDoc, String> {

    @Query("{name:'?0'}")
    TestDoc findItemByName(String name);

    @Query(value="{category:'?0'}", fields="{'name' : 1, 'quantity' : 1}")
    List<TestDoc> findAll(String category);

    public long count();

}
