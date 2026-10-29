# GIÁO TRÌNH NHẬP MÔN KHOA HỌC MÁY TÍNH VÀ CẤU TRÚC DỮ LIỆU
**Mã học phần:** CSE101  
**Tác giả:** Viện Kỹ thuật và Khoa học Máy tính, VinUniversity  
**Năm xuất bản:** 2024  

---

### [Trang 15, Đoạn 1] - Đánh giá Độ phức tạp thuật toán (Big O Notation)
Ký hiệu Big-O biểu diễn chặn trên tiệm cận (Asymptotic Upper Bound) của thời gian chạy hoặc dung lượng bộ nhớ mà một thuật toán tiêu thụ khi kích thước đầu vào n tăng dần tới vô cùng.
Các cấp độ phức tạp thời gian phổ biến từ tối ưu nhất đến kém hiệu quả nhất:
1. O(1) - Thời gian hằng số (Constant Time): Thời gian thực thi không phụ thuộc vào n. Ví dụ: Truy cập phần tử mảng qua chỉ số (arr[i]), phép kiểm tra độ dài mảng đã lưu trước.
2. O(log n) - Thời gian hàm logarit (Logarithmic Time): Thuật toán chia đôi không gian tìm kiếm sau mỗi bước. Ví dụ: Tìm kiếm nhị phân (Binary Search).
3. O(n) - Thời gian tuyến tính (Linear Time): Thời gian tăng tỷ lệ thuận với số lượng phần tử. Ví dụ: Duyệt qua danh sách (Linear Search), tìm giá trị lớn nhất trong mảng chưa sắp xếp.
4. O(n log n) - Thời gian tuyến tính logarit: Chuẩn mực tối ưu cho các thuật toán sắp xếp dựa trên so sánh (Comparison Sort). Ví dụ: Merge Sort, Quick Sort (trung bình), Heap Sort.
5. O(n^2) - Thời gian bậc hai (Quadratic Time): Thường xuất hiện trong các thuật toán có 2 vòng lặp lồng nhau duyệt qua dữ liệu. Ví dụ: Bubble Sort, Selection Sort, Insertion Sort.
6. O(2^n) - Thời gian hàm mũ (Exponential Time): Thời gian tăng gấp đôi mỗi khi n tăng thêm 1 đơn vị. Ví dụ: Đệ quy ngây thơ tính số Fibonacci, bài toán Tháp Hà Nội.

### [Trang 38, Đoạn 2] - So sánh Thuật toán sắp xếp Quick Sort và Merge Sort
- Merge Sort (Sắp xếp trộn):
  + Nguyên lý: Áp dụng mô hình Chia để trị (Divide and Conquer). Chia danh sách làm hai nửa đều nhau, đệ quy sắp xếp từng nửa, sau đó gộp (merge) hai nửa đã sắp xếp lại.
  + Độ phức tạp thời gian: O(n log n) trong mọi trường hợp (tốt nhất, trung bình, xấu nhất).
  + Tính ổn định (Stability): Là thuật toán sắp xếp ổn định (Stable Sort), giữ nguyên thứ tự tương đối của các phần tử có giá trị bằng nhau.
  + Nhược điểm: Cần bộ nhớ phụ trợ O(n) để thực hiện thao tác trộn (Out-of-place).

- Quick Sort (Sắp xếp nhanh):
  + Nguyên lý: Chọn một phần tử chốt (Pivot), phân hoạch (Partition) mảng sao cho các phần tử nhỏ hơn pivot nằm bên trái, các phần tử lớn hơn pivot nằm bên phải, sau đó đệ quy trên hai mảng con.
  + Độ phức tạp thời gian: Trung bình đạt O(n log n). Trường hợp xấu nhất (Worst-case) lên tới O(n^2) xảy ra khi chọn pivot tồi (ví dụ: mảng đã sắp xếp sẵn mà luôn chọn pivot là phần tử đầu tiên hoặc cuối cùng).
  + Ưu điểm: Sắp xếp tại chỗ (In-place) với không gian bộ nhớ ngăn xếp O(log n), tốc độ thực nghiệm thường nhanh hơn Merge Sort nhờ tối ưu bộ nhớ đệm (Cache locality).
