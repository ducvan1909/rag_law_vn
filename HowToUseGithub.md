# Smart Traffic Simulation
This is an OOP Project for 2025.2 course, implementing a smart city traffic simulation system.

Ví dụ: Dưới đây là cách triển khai thực tế cho nhóm **Vehicle** (3 người):

### 1. Quy trình tạo nhánh "Cha - Con"

1.  **Bước 1 (Nhóm trưởng):** Từ nhánh `develop`, tạo một nhánh "Cha" chung cho cả nhóm gọi là `vehicle/integration`. Đây sẽ là "thủ phủ" của nhóm Vehicle.
2.  **Bước 2 (3 Thành viên):** Cả 3 người sẽ **không** tạo nhánh từ `develop`, mà tạo nhánh từ `vehicle/integration`.

### 2. Cấu trúc cây thư mục nhánh

```text
develop (Nhánh chung toàn dự án)
   |
   └── vehicle/integration (Nhánh chung của nhóm Vehicle - Nhánh "Cha")
          |
          ├── vehicle/A/base-logic (Nhánh "Con" của người A)
          ├── vehicle/B/behavior   (Nhánh "Con" của người B)
          └── vehicle/C/renderer   (Nhánh "Con" của người C)
```

### 3. Lý do

*   **Tự do thử nghiệm:** 3 người nhóm Vehicle có thể thoải mái gộp code qua lại, sửa lỗi cho nhau trên nhánh `integration` mà không sợ làm hỏng code của nhóm Map.
*   **Gộp code sạch sẽ:** Khi nhóm Vehicle đã làm xong xuôi, xe chạy mượt, các bạn chỉ cần gửi **1 cái Pull Request duy nhất** từ `vehicle/integration` vào `develop`. Nhóm Map nhìn vào sẽ thấy rất gọn gàng.
*   **Giải quyết xung đột sớm:** Nếu người A và người B sửa chung một file, họ sẽ phát hiện và sửa lỗi ngay khi gộp vào nhánh `integration` của nhóm, thay vì đợi đến lúc gộp vào nhánh chung của cả lớp mới phát hiện ra.

---

### 4. Các lệnh Git thực tế để làm việc này:

**Cho Nhóm trưởng (Tạo nhánh cha):**
```bash
git checkout develop              # Sang nhánh develop
git pull origin develop           # Cập nhật code mới nhất
git checkout -b vehicle/integration # Tạo nhánh cha cho nhóm
git push origin vehicle/integration # Đẩy nhánh cha lên GitHub
```

**Cho Thành viên A (Tạo nhánh con từ nhánh cha):**
```bash
git fetch origin                           # Lấy thông tin các nhánh mới về
git checkout vehicle/integration           # Sang nhánh cha của nhóm
git checkout -b vehicle/A/base-logic       # Tạo nhánh con từ nhánh cha
```

---

### 5. Quy trình gộp code hàng ngày:

1.  **Người A** làm xong tính năng -> Gửi Pull Request vào `vehicle/integration`.
2.  **Người B và C** vào kiểm tra code của người A trên GitHub, nếu thấy OK thì bấm **Merge**.
3.  Sau khi gộp xong, **Người B và C** nên cập nhật code mới từ nhánh cha về nhánh con của mình để tránh bị lạc hậu:
    ```bash
    git checkout vehicle/integration
    git pull origin vehicle/integration
    git checkout vehicle/B/behavior
    git merge vehicle/integration
    ```

### 6. Khi nào thì gộp vào `develop`?
Khi cả 3 người A, B, C đã hoàn thành và nhánh `vehicle/integration` đã có một bộ khung hoàn chỉnh (Xe đã hiện hình, đã biết chạy, đã có AI), lúc đó nhóm trưởng mới gửi Pull Request từ `vehicle/integration` vào `develop` để kết hợp với nhóm Map.

## Authors
- Phuc, Phung Minh
- Truong, Tran Xuan
- Phi, Duong Tuan
- Nghia, Le Trong
- Van, Nguyen Duc
- Trung, Tran Van