

# InterviewFox 🦊

A Spring Boot backend project based on a production-ready template.  
This project is used to practice full-stack backend development, including user management, session handling, and scalable system design.

---

## 🚀 Tech Stack

- Java 11
- Spring Boot 2.7
- MyBatis / MyBatis-Plus
- MySQL
- Redis (Session)
- Swagger + Knife4j (API testing)

---

## 📦 Features (Current Progress)

- [x] Project setup & environment configuration  
- [x] MySQL database integration  
- [x] User register / login / logout  
- [x] Redis-based session login  
- [ ] Post module (CRUD)  
- [x] Kotlin question search with optional Elasticsearch

---

## 🛠️ Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/Bailin-Xu/InterviewFox.git
cd InterviewFox
````

---

### 2. Configure application.yml

Update your local configuration:

```yaml
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/interviewfox
    username: root
    password: your_password

  redis:
    host: localhost
    port: 6379
```

---

### 3. Initialize database

Run SQL script:

```text
sql/create_table.sql
```

---

### 4. Run the project

```bash
mvn spring-boot:run
```

---

### 5. API Documentation

Open in browser:

```text
http://localhost:8101/api/doc.html
```

---

## Question search with Elasticsearch

The existing MySQL search remains the default. To compare both engines on the same
endpoint and database, start an Elasticsearch 7.17 node and run
`sql/question_search_sync.sql` once against the initialized MySQL database. The
migration creates InnoDB sync tables and triggers on `question`. Use a MySQL account
with migration privileges to apply it. The application's database account needs
read and write access to the two new tables.

For local verification, you can run a disposable ES node in a separate terminal:

```bash
docker run --rm --name interviewfox-es -p 127.0.0.1:9200:9200 \
  -e discovery.type=single-node -e xpack.security.enabled=false \
  -e ES_JAVA_OPTS="-Xms512m -Xmx512m" \
  docker.elastic.co/elasticsearch/elasticsearch:7.17.4
```

```bash
mysql -u root -p interviewfox < sql/question_search_sync.sql
SPRING_ELASTICSEARCH_URIS=http://localhost:9200 \
INTERVIEWFOX_SEARCH_ELASTICSEARCH_ENABLED=true \
mvn spring-boot:run
```

Set `SPRING_ELASTICSEARCH_USERNAME` and `SPRING_ELASTICSEARCH_PASSWORD` if your
node requires authentication. The sync worker runs every second by default
(`INTERVIEWFOX_SEARCH_ELASTICSEARCH_SYNC_DELAY_MS`). It creates
`interviewfox-question-v1`, backfills in ID order, and drains the MySQL change queue.
Wait for `Question Elasticsearch index is ready` in the application log.

```bash
for engine in mysql elasticsearch; do
  curl -sS "http://localhost:8101/api/question/list/page/vo?engine=$engine" \
    -H 'Content-Type: application/json' \
    -d '{"searchText":"Redis","current":1,"pageSize":10}'
done
```

Use a test database with at least one active question before startup. Confirm it
appears in both responses. Then add, edit, and delete a question through the app
and repeat the ES request after each change. Allow time for the poll and the
index refresh. To verify retries, make ES temporarily unavailable, write a
question, restore ES, and confirm the change appears without editing it again.
The following queries show full sync progress and the pending change count.

```sql
SELECT index_uuid, backfill_cursor, backfill_complete FROM question_search_sync_state;
SELECT COUNT(*) AS pending_changes FROM question_search_outbox;
```

MySQL uses substring matching. ES uses the `question_text` analyzer (standard
tokenizer, lowercasing, and accent folding), weights titles higher, and matches
tags exactly. Both engines return the same page shape, but hits and order may
differ. ES supports the first 10,000 results per query and sorts by relevance
when no sort is provided. An explicit ES request reports an error while ES is
disabled or initializing, so comparisons cannot silently fall back to MySQL.
The index stores a copy of question fields, while the response still loads
author information from MySQL. The queue tracks row inserts, updates and deletes,
including soft deletes. Operations such as `TRUNCATE` require rebuilding the index.

Run the API regression tests with `mvn -Dtest=QuestionSearchControllerTest test`.

## 📌 Notes

* Redis is required for login session
* Elasticsearch is optional (for search features)
* Configuration files are not included in Git for security reasons

---

## 📈 Future Work

* Implement post system (CRUD + interaction)
* Add permission control
* Improve system design & performance

---

## 👨‍💻 Author

* Bailin Xu
