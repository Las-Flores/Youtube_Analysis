--@block
CREATE TABLE Channels (
    id INT PRIMARY KEY AUTO_INCREMENT,
    channel_name VARCHAR(255),
    subscriber_count INT,
    country TEXT
);

CREATE TABLE Videos (
    id INT PRIMARY KEY AUTO_INCREMENT,
    channel_id INT,
    title VARCHAR(255),
    description TEXT,
    day DATE,
    hour TIME,
    duration TIME,
    like_count INT,
    view_count INT,
    comment_count INT,
    video_url VARCHAR(255) UNIQUE,
    thumbnail_url VARCHAR(255),
    query VARCHAR(255),
    FOREIGN KEY (channel_id) REFERENCES Channels(id)
);

CREATE TABLE Comments (
    id INT PRIMARY KEY AUTO_INCREMENT,
    video_id INT,
    comment TEXT,
    FOREIGN KEY (video_id) REFERENCES Videos(id)
);


--@block
SELECT email, id FROM users

WHERE country = 'us'
AND email LIKE 'w%'

ORDER BY id DESC
LIMIT 2;

--@block
CREATE INDEX email_index ON users(email)


--@block
INSERT INTO Rooms (owner_id, street)
VALUES 
    (1, 'san diego sailboat'),
    (1, 'nantucket cottage'),
    (1, 'vail cabin'),
    (1, 'sf cardboard box');

--@block
SELECT * FROM videos

--@block
SELECT * FROM Channels
