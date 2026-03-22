

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
- [ ] Elasticsearch integration  

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
    url: jdbc:mysql://localhost:3306/my_db
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

## 📌 Notes

* Redis is required for login session
* Elasticsearch is optional (for search features)
* Configuration files are not included in Git for security reasons

---

## 📈 Future Work

* Implement post system (CRUD + interaction)
* Add permission control
* Integrate Elasticsearch for search
* Improve system design & performance

---

## 👨‍💻 Author

* Bailin Xu