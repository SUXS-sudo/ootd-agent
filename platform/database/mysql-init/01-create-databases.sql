CREATE DATABASE IF NOT EXISTS ootd_checkpoints CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS ootd_test CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS ootd_checkpoints_test CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

GRANT ALL PRIVILEGES ON ootd.* TO 'ootd'@'%';
GRANT ALL PRIVILEGES ON ootd_checkpoints.* TO 'ootd'@'%';
GRANT ALL PRIVILEGES ON ootd_test.* TO 'ootd'@'%';
GRANT ALL PRIVILEGES ON ootd_checkpoints_test.* TO 'ootd'@'%';
FLUSH PRIVILEGES;
