"""Teacher-reviewable Assessment blueprints for the four-course demo window.

The catalogue is content, not a mastery decision.  It supplies grounded draft
questions and rubrics for the instructor review screen.  Nothing in this file
publishes an item or updates a learner's knowledge state.
"""

from __future__ import annotations

from datetime import date
from typing import Any

DEMO_ASSESSMENT_BLUEPRINTS: tuple[dict[str, Any], ...] = (
    {
        "key": "db201-2026-10-12-chapter-1",
        "course_code": "DB201",
        "week_start": "2026-10-12",
        "week_end": "2026-10-18",
        "assignment_title": "Bài tập Chương 1: Khái quát về hệ cơ sở dữ liệu",
        "topic": "DB201 · Tuần 12/10 · Khái quát hệ cơ sở dữ liệu",
        "question": (
            "Một hệ thống đang lưu dữ liệu khách hàng trong nhiều tệp riêng lẻ. "
            "Hãy nêu hai vấn đề của cách lưu này và giải thích DBMS xử lý từng vấn đề như thế nào."
        ),
        "rubric": [
            "Nêu đúng ít nhất hai vấn đề của hệ tệp như dư thừa, không nhất quán, khó chia sẻ hoặc khó kiểm soát truy cập.",
            "Giải thích đúng vai trò tương ứng của DBMS thay vì chỉ liệt kê thuật ngữ.",
            "Lập luận gắn với tình huống khách hàng và không đưa ra kết luận ngoài phạm vi tài liệu.",
        ],
        "knowledge_component_ids": ["db201-dbms-purpose-data-independence"],
        "assessment_stage": "application",
        "source": "Chuong01_Khai_quat_ve_cac_he_CSDL.pdf",
        "hints": [
            "So sánh việc cùng một dữ liệu xuất hiện ở nhiều tệp.",
            "Xem lại các chức năng quản lý, chia sẻ và kiểm soát dữ liệu của DBMS.",
        ],
    },
    {
        "key": "dsa201-2026-10-12-chapter-1",
        "course_code": "DSA201",
        "week_start": "2026-10-12",
        "week_end": "2026-10-18",
        "assignment_title": "Bài tập Chương 1: Tổng quan cấu trúc dữ liệu và giải thuật",
        "topic": "DSA201 · Tuần 12/10 · Tổng quan CTDL và giải thuật",
        "question": (
            "Với một danh sách dữ liệu tăng từ 100 lên 10.000 phần tử, hãy giải thích vì sao lựa chọn cấu trúc dữ liệu "
            "và độ phức tạp của thao tác quan trọng hơn việc chỉ nhìn thời gian chạy của một lần thử."
        ),
        "rubric": [
            "Phân biệt được cấu trúc dữ liệu với giải thuật/thao tác thực hiện trên dữ liệu.",
            "Giải thích được ý nghĩa tăng trưởng của độ phức tạp khi kích thước đầu vào tăng.",
            "Nêu được ít nhất một tiêu chí lựa chọn phù hợp như truy cập, tìm kiếm, chèn hoặc xóa.",
        ],
        "knowledge_component_ids": ["dsa201-data-structure-complexity-choice"],
        "assessment_stage": "why",
        "source": "Buoi01_Tong_quan_CTDL_GT.pdf",
        "hints": [
            "Hãy nghĩ đến số phép toán khi n tăng, không chỉ số giây của một máy cụ thể.",
            "Xác định thao tác nào được dùng thường xuyên nhất trong tình huống.",
        ],
    },
    {
        "key": "oopcpp201-2026-10-12-chapter-1",
        "course_code": "OOPCPP201",
        "week_start": "2026-10-12",
        "week_end": "2026-10-18",
        "assignment_title": "Bài tập Chương 1: Giới thiệu lập trình hướng đối tượng",
        "topic": "OOPCPP201 · Tuần 12/10 · Tư duy hướng đối tượng",
        "question": (
            "Khi mô hình hóa tài khoản ngân hàng, vì sao số dư nên được đóng gói thay vì cho mọi đoạn mã sửa trực tiếp? "
            "Hãy nêu một thao tác công khai phù hợp và bất biến cần bảo vệ."
        ),
        "rubric": [
            "Giải thích đúng mục tiêu của đóng gói và kiểm soát trạng thái đối tượng.",
            "Đề xuất được thao tác công khai hợp lý như gửi hoặc rút tiền thay vì sửa trực tiếp số dư.",
            "Nêu được bất biến hoặc điều kiện hợp lệ cần bảo vệ và liên hệ đúng với tình huống.",
        ],
        "knowledge_component_ids": ["oopcpp201-encapsulation-object-invariants"],
        "assessment_stage": "application",
        "source": "Buoi01_Gioi_thieu_OOP.pdf",
        "hints": [
            "Xem điều gì có thể xảy ra nếu số dư bị gán tùy ý.",
            "Một phương thức công khai có thể kiểm tra điều kiện nào trước khi đổi trạng thái?",
        ],
    },
    {
        "key": "web201-2026-10-12-chapter-0",
        "course_code": "WEB201",
        "week_start": "2026-10-12",
        "week_end": "2026-10-18",
        "assignment_title": "Bài tập Chương 0: Giới thiệu môn học",
        "topic": "WEB201 · Tuần 12/10 · Phạm vi phát triển Web",
        "question": (
            "Một người dùng nhập địa chỉ trang web và nhận được giao diện có dữ liệu động. "
            "Hãy mô tả ngắn vai trò của trình duyệt, máy chủ web và lớp dữ liệu trong luồng này."
        ),
        "rubric": [
            "Mô tả đúng vai trò của trình duyệt trong gửi yêu cầu và hiển thị kết quả.",
            "Mô tả đúng vai trò của máy chủ trong xử lý yêu cầu và tạo phản hồi.",
            "Giải thích được lớp dữ liệu cung cấp/lưu dữ liệu động mà không trộn lẫn ba vai trò.",
        ],
        "knowledge_component_ids": ["web201-browser-server-data-flow"],
        "assessment_stage": "explain",
        "source": "00_gioi_thieu.pdf",
        "hints": [
            "Theo dõi yêu cầu từ thiết bị người dùng tới nơi xử lý.",
            "Phân biệt nơi hiển thị, nơi xử lý nghiệp vụ và nơi lưu dữ liệu.",
        ],
    },
    {
        "key": "db201-2026-10-19-chapter-2",
        "course_code": "DB201",
        "week_start": "2026-10-19",
        "week_end": "2026-10-25",
        "assignment_title": "Bài tập Chương 2: Mô hình cơ sở dữ liệu",
        "topic": "DB201 · Tuần 19/10 · Mô hình cơ sở dữ liệu",
        "question": (
            "Trong hệ thống đăng ký môn học có SinhVien, MonHoc và việc đăng ký giữa hai bên. "
            "Hãy xác định các thành phần mô hình chính và giải thích vì sao đăng ký không nên chỉ là một thuộc tính văn bản của SinhVien."
        ),
        "rubric": [
            "Xác định đúng các thực thể chính SinhVien và MonHoc.",
            "Nhận ra đăng ký là quan hệ có thể mang thuộc tính riêng hoặc cần được mô hình hóa tương đương.",
            "Giải thích được vấn đề của việc nhét danh sách đăng ký vào một thuộc tính văn bản.",
        ],
        "knowledge_component_ids": ["db201-entity-relationship-modeling"],
        "assessment_stage": "application",
        "source": "Chuong02_Mo_hinh_CSDL.pdf",
        "hints": [
            "Một sinh viên có thể học nhiều môn và một môn có nhiều sinh viên.",
            "Đăng ký có thể cần lưu thêm ngày đăng ký hoặc trạng thái.",
        ],
    },
    {
        "key": "dsa201-2026-10-19-chapter-2",
        "course_code": "DSA201",
        "week_start": "2026-10-19",
        "week_end": "2026-10-25",
        "assignment_title": "Bài tập Chương 2: Kỹ thuật tìm kiếm",
        "topic": "DSA201 · Tuần 19/10 · Kỹ thuật tìm kiếm",
        "question": (
            "Cho một mảng đã sắp xếp gồm 1.024 phần tử. Hãy chọn tìm kiếm tuyến tính hoặc tìm kiếm nhị phân, "
            "mô tả cách thu hẹp phạm vi và giải thích độ phức tạp của lựa chọn."
        ),
        "rubric": [
            "Chọn đúng tìm kiếm nhị phân nhờ điều kiện mảng đã sắp xếp.",
            "Mô tả đúng việc so sánh phần tử giữa và loại bỏ một nửa phạm vi sau mỗi bước.",
            "Giải thích đúng độ phức tạp O(log n) và không nhầm với O(n).",
        ],
        "knowledge_component_ids": ["dsa201-binary-search-precondition-complexity"],
        "assessment_stage": "application",
        "source": "Buoi02_Ky_thuat_tim_kiem.pdf",
        "hints": [
            "Điều kiện nào cho phép loại bỏ một nửa dữ liệu sau mỗi lần so sánh?",
            "Hãy liên hệ 1.024 với số lần chia đôi liên tiếp.",
        ],
    },
    {
        "key": "oopcpp201-2026-10-19-chapter-2",
        "course_code": "OOPCPP201",
        "week_start": "2026-10-19",
        "week_end": "2026-10-25",
        "assignment_title": "Bài tập Chương 2: Mở rộng C++ phần 1",
        "topic": "OOPCPP201 · Tuần 19/10 · Mở rộng C++ phần 1",
        "question": (
            "Một hàm C++ cần cập nhật trực tiếp giá trị biến của hàm gọi nhưng không nhận quyền sở hữu vùng nhớ. "
            "Hãy chọn truyền tham chiếu hoặc con trỏ, trình bày khai báo minh họa ngắn và giải thích lựa chọn."
        ),
        "rubric": [
            "Chọn được cơ chế truyền phù hợp với yêu cầu cập nhật nhưng không sở hữu vùng nhớ.",
            "Khai báo hoặc ví dụ sử dụng nhất quán với lựa chọn tham chiếu/con trỏ.",
            "Giải thích được tác động lên biến gốc và lưu ý hợp lệ/an toàn tương ứng.",
        ],
        "knowledge_component_ids": ["oopcpp201-reference-pointer-parameter-semantics"],
        "assessment_stage": "application",
        "source": "Buoi02_Mo_rong_Cpp_phan1.pdf",
        "hints": [
            "Xem cơ chế nào tạo bí danh trực tiếp cho biến đã tồn tại.",
            "Nếu dùng con trỏ, cần kiểm tra điều kiện an toàn nào?",
        ],
    },
    {
        "key": "web201-2026-10-19-chapter-1",
        "course_code": "WEB201",
        "week_start": "2026-10-19",
        "week_end": "2026-10-25",
        "assignment_title": "Bài tập Chương 1: Công nghệ Web",
        "topic": "WEB201 · Tuần 19/10 · Công nghệ Web",
        "question": (
            "Một trình duyệt gửi biểu mẫu tạo tài khoản tới máy chủ. Hãy chọn phương thức HTTP phù hợp, "
            "mô tả request/response chính và giải thích vì sao thao tác này không nên dùng GET."
        ),
        "rubric": [
            "Chọn đúng POST cho thao tác tạo tài nguyên hoặc gửi dữ liệu làm thay đổi trạng thái.",
            "Mô tả được thành phần request/response ở mức phù hợp như URL, body và status code.",
            "Giải thích được hạn chế của GET dựa trên ngữ nghĩa an toàn/idempotence hoặc dữ liệu trên URL.",
        ],
        "knowledge_component_ids": ["web201-http-request-response-methods"],
        "assessment_stage": "application",
        "source": "01_cong_nghe_web.pdf",
        "hints": [
            "Phương thức nào thường được dùng khi tạo dữ liệu mới?",
            "So sánh vị trí dữ liệu và ý nghĩa của GET với POST.",
        ],
    },
)


_ADAPTIVE_STAGE_BANKS: tuple[dict[str, Any], ...] = (
    {
        "key": "db201-2026-10-19-chapter-2",
        "course_code": "DB201",
        "assignment_title": "Bài tập Chương 2: Mô hình cơ sở dữ liệu",
        "topic": "DB201 · Tuần 19/10 · Mô hình cơ sở dữ liệu",
        "source": "Chuong02_Mo_hinh_CSDL.pdf",
        "kc": "db201-entity-relationship-modeling",
        "stages": {
            "recall": {
                "question": "Trong mô hình ER, thực thể, thuộc tính và mối quan hệ lần lượt biểu diễn điều gì?",
                "rubric": [
                    "Nêu đúng thực thể là đối tượng/khái niệm cần quản lý.",
                    "Nêu đúng thuộc tính mô tả đặc trưng của thực thể hoặc quan hệ.",
                    "Nêu đúng mối quan hệ thể hiện sự liên kết giữa các thực thể.",
                ],
                "hints": ["Hãy tách đối tượng, đặc trưng và sự liên kết.", "Dùng một ví dụ ngắn nếu cần."],
            },
            "explain": {
                "question": "Hãy giải thích quan hệ nhiều-nhiều giữa SinhVien và MonHoc bằng lời của bạn.",
                "rubric": [
                    "Giải thích được một SinhVien có thể đăng ký nhiều MonHoc.",
                    "Giải thích được một MonHoc có thể có nhiều SinhVien.",
                    "Không nhầm quan hệ nhiều-nhiều với hai quan hệ một-một độc lập.",
                ],
                "hints": ["Xét từ cả phía SinhVien và MonHoc.", "Mỗi phía có thể liên kết với bao nhiêu bản ghi phía kia?"],
            },
            "why": {
                "question": "Vì sao quan hệ DangKy thường cần được mô hình hóa thành một thực thể kết hợp thay vì lưu danh sách mã môn trong SinhVien?",
                "rubric": [
                    "Lập luận được việc danh sách lặp trong một thuộc tính gây khó truy vấn/cập nhật.",
                    "Nêu được DangKy có thể mang thuộc tính riêng như ngày đăng ký hoặc trạng thái.",
                    "Liên hệ được mô hình kết hợp với việc biểu diễn đúng quan hệ nhiều-nhiều.",
                ],
                "hints": ["DangKy có dữ liệu riêng nào?", "Điều gì xảy ra khi một sinh viên đổi hoặc hủy môn?"],
            },
            "transfer": {
                "question": "Chuyển sang hệ thống bệnh viện có BacSi, BenhNhan và mỗi lần Kham. Hãy đề xuất mô hình ER tối thiểu và chỉ ra nơi lưu ngày khám, chẩn đoán.",
                "rubric": [
                    "Xác định đúng BacSi và BenhNhan là các thực thể chính.",
                    "Mô hình hóa lần Kham như quan hệ có thuộc tính hoặc thực thể kết hợp phù hợp.",
                    "Đặt ngày khám và chẩn đoán ở lần Kham, không gắn sai cố định vào BacSi/BenhNhan.",
                ],
                "hints": ["Một bệnh nhân có thể khám nhiều bác sĩ nhiều lần.", "Dữ liệu nào thay đổi theo từng lần khám?"],
            },
        },
    },
    {
        "key": "dsa201-2026-10-19-chapter-2",
        "course_code": "DSA201",
        "assignment_title": "Bài tập Chương 2: Kỹ thuật tìm kiếm",
        "topic": "DSA201 · Tuần 19/10 · Kỹ thuật tìm kiếm",
        "source": "Buoi02_Ky_thuat_tim_kiem.pdf",
        "kc": "dsa201-binary-search-precondition-complexity",
        "stages": {
            "recall": {
                "question": "Điều kiện đầu vào quan trọng nhất để áp dụng tìm kiếm nhị phân là gì, và mỗi bước so sánh với phần tử nào?",
                "rubric": [
                    "Nêu đúng dữ liệu phải được sắp xếp theo thứ tự nhất quán.",
                    "Nêu đúng mỗi bước so sánh với phần tử giữa của phạm vi hiện tại.",
                    "Không nhầm điều kiện sắp xếp với yêu cầu các phần tử phải khác nhau.",
                ],
                "hints": ["Thuật toán cần biết nửa nào chắc chắn không chứa khóa.", "Vị trí nào chia phạm vi thành hai phần?"],
            },
            "explain": {
                "question": "Hãy mô tả bằng lời cách cập nhật biên trái và biên phải của tìm kiếm nhị phân sau một lần so sánh không khớp.",
                "rubric": [
                    "Mô tả đúng trường hợp khóa nhỏ hơn phần tử giữa thì giữ nửa trái.",
                    "Mô tả đúng trường hợp khóa lớn hơn phần tử giữa thì giữ nửa phải.",
                    "Thể hiện biên được cập nhật để loại phần tử giữa đã kiểm tra và bảo đảm tiến triển.",
                ],
                "hints": ["Xét riêng trường hợp khóa nhỏ hơn và lớn hơn.", "Phần tử giữa đã kiểm tra có cần giữ lại không?"],
            },
            "why": {
                "question": "Vì sao việc loại bỏ một nửa phạm vi sau mỗi bước dẫn đến độ phức tạp O(log n), không phải O(n/2)?",
                "rubric": [
                    "Phân biệt được giảm theo phép chia lặp với giảm một lượng hằng số.",
                    "Liên hệ số bước k với n/2^k và điều kiện phạm vi còn khoảng một phần tử.",
                    "Kết luận đúng số bước tăng theo log cơ số 2 của n.",
                ],
                "hints": ["Viết kích thước còn lại sau k lần chia đôi.", "Giải n/2^k ≈ 1 theo k."],
            },
            "transfer": {
                "question": "Một mảng tăng dần có thể chứa giá trị trùng lặp. Hãy điều chỉnh tìm kiếm nhị phân để tìm vị trí xuất hiện đầu tiên của khóa và giải thích vì sao vẫn là O(log n).",
                "rubric": [
                    "Khi tìm thấy khóa vẫn tiếp tục tìm về nửa trái để tìm vị trí sớm hơn.",
                    "Lưu lại vị trí khớp tốt nhất hoặc dùng điều kiện biên tương đương một cách nhất quán.",
                    "Giải thích đúng phạm vi vẫn giảm một nửa mỗi bước nên độ phức tạp giữ O(log n).",
                ],
                "hints": ["Tìm thấy chưa chắc đã là lần xuất hiện đầu tiên.", "Hãy lưu đáp án tạm rồi tiếp tục về phía nào?"],
            },
        },
    },
    {
        "key": "oopcpp201-2026-10-19-chapter-2",
        "course_code": "OOPCPP201",
        "assignment_title": "Bài tập Chương 2: Mở rộng C++ phần 1",
        "topic": "OOPCPP201 · Tuần 19/10 · Tham chiếu và con trỏ",
        "source": "Buoi02_Mo_rong_Cpp_phan1.pdf",
        "kc": "oopcpp201-reference-pointer-parameter-semantics",
        "stages": {
            "recall": {
                "question": "Trong C++, ký hiệu khai báo tham số tham chiếu là gì và thay đổi qua tham số đó tác động thế nào tới biến gốc?",
                "rubric": [
                    "Nêu đúng ký hiệu & trong khai báo tham số tham chiếu.",
                    "Nêu đúng tham số là bí danh của biến được truyền vào.",
                    "Nêu đúng phép gán qua tham chiếu làm thay đổi biến gốc.",
                ],
                "hints": ["Ví dụ dạng void f(int ... x).", "Tham số có phải là một bản sao độc lập không?"],
            },
            "explain": {
                "question": "Hãy giải thích hai khác biệt quan trọng giữa tham chiếu và con trỏ khi dùng làm tham số hàm C++.",
                "rubric": [
                    "Phân biệt đúng cú pháp truy cập trực tiếp của tham chiếu với giải tham chiếu con trỏ.",
                    "Nêu được con trỏ có thể biểu diễn null còn tham chiếu hợp lệ phải gắn với đối tượng.",
                    "Không nhầm việc không sở hữu vùng nhớ với việc không thể thay đổi biến gốc.",
                ],
                "hints": ["So sánh null và cú pháp *p.", "Cả hai có thể cho phép sửa biến gốc trong điều kiện nào?"],
            },
            "why": {
                "question": "Vì sao một hàm bắt buộc nhận đúng một đối tượng đã tồn tại thường ưu tiên tham chiếu thay vì con trỏ?",
                "rubric": [
                    "Lập luận được tham chiếu biểu đạt ràng buộc phải có đối tượng hợp lệ.",
                    "Nêu được cú pháp gọi/truy cập rõ hơn và không cần kiểm tra null trong contract đó.",
                    "Thừa nhận con trỏ phù hợp hơn khi cần trạng thái không có đối tượng hoặc đổi đích trỏ.",
                ],
                "hints": ["Contract có cho phép không truyền đối tượng không?", "Khi nào null lại mang ý nghĩa hợp lệ?"],
            },
            "transfer": {
                "question": "Thiết kế chữ ký hàm C++ cập nhật đồng thời min và max từ một vector đầu vào nhưng không sao chép vector. Hãy chọn tham chiếu/con trỏ cho từng tham số và giải thích.",
                "rubric": [
                    "Dùng const reference cho vector đầu vào để tránh sao chép và không sửa dữ liệu nguồn.",
                    "Chọn reference hoặc pointer nhất quán cho hai kết quả min/max và thể hiện đúng khả năng cập nhật biến gọi.",
                    "Giải thích được contract hợp lệ, bao gồm cách xử lý vector rỗng hoặc kết quả không tồn tại.",
                ],
                "hints": ["Đầu vào chỉ đọc có thể dùng const gì?", "Vector rỗng ảnh hưởng contract kết quả thế nào?"],
            },
        },
    },
    {
        "key": "web201-2026-10-19-chapter-1",
        "course_code": "WEB201",
        "assignment_title": "Bài tập Chương 1: Công nghệ Web",
        "topic": "WEB201 · Tuần 19/10 · HTTP request/response",
        "source": "01_cong_nghe_web.pdf",
        "kc": "web201-http-request-response-methods",
        "stages": {
            "recall": {
                "question": "Một HTTP request và response tối thiểu gồm những thành phần chính nào?",
                "rubric": [
                    "Nêu được request có method và target/URL.",
                    "Nêu được header và body là các thành phần tùy ngữ cảnh, không đồng nhất với nhau.",
                    "Nêu được response có status code và nội dung/body phản hồi.",
                ],
                "hints": ["Bắt đầu từ dòng yêu cầu và dòng trạng thái.", "Thông tin mô tả và nội dung dữ liệu nằm ở đâu?"],
            },
            "explain": {
                "question": "Hãy giải thích sự khác nhau về mục đích giữa GET và POST trong một ứng dụng web.",
                "rubric": [
                    "Giải thích GET chủ yếu dùng để lấy/đọc biểu diễn tài nguyên.",
                    "Giải thích POST dùng để gửi dữ liệu cho xử lý thường tạo hoặc thay đổi trạng thái.",
                    "Không kết luận sai rằng POST tự động mã hóa hoặc bảo mật dữ liệu nếu không có HTTPS.",
                ],
                "hints": ["Một phương thức chỉ đọc và một phương thức gửi dữ liệu xử lý.", "Bảo mật đường truyền do HTTP method hay HTTPS quyết định?"],
            },
            "why": {
                "question": "Vì sao không nên dùng GET cho thao tác xóa tài khoản, kể cả khi máy chủ vẫn có thể viết endpoint như vậy?",
                "rubric": [
                    "Lập luận được GET có ngữ nghĩa an toàn và không nên gây thay đổi trạng thái.",
                    "Nêu được trình duyệt, cache, crawler hoặc prefetch có thể tự động truy cập URL GET.",
                    "Liên hệ được lựa chọn method đúng với khả năng dự đoán và an toàn của hệ thống.",
                ],
                "hints": ["Ai ngoài người dùng có thể tự truy cập một URL?", "Safe method có được gây tác dụng phụ không?"],
            },
            "transfer": {
                "question": "Một trang có biểu mẫu tìm kiếm sản phẩm và biểu mẫu tạo tài khoản. Hãy chọn method cho từng biểu mẫu, mô tả nơi đặt dữ liệu chính và giải thích lựa chọn.",
                "rubric": [
                    "Chọn GET hợp lý cho tìm kiếm chỉ đọc để tham số có thể nằm trên URL/chia sẻ được.",
                    "Chọn POST cho tạo tài khoản vì gửi dữ liệu và làm thay đổi trạng thái máy chủ.",
                    "Phân biệt đúng body/query với bảo mật; dữ liệu nhạy cảm vẫn cần HTTPS và xử lý phù hợp.",
                ],
                "hints": ["Kết quả nào nên có URL có thể bookmark?", "Thao tác nào tạo dữ liệu mới trên máy chủ?"],
            },
        },
    },
)

ADAPTIVE_SEQUENCE_STAGES = ["recall", "explain", "why", "application", "transfer"]


def adaptive_stages_for_content_key(content_key: str) -> list[str] | None:
    """Keep the four-course demo on one instructor-approved five-stage sequence."""

    for bank in _ADAPTIVE_STAGE_BANKS:
        prefix = str(bank["key"])
        if content_key == prefix or content_key.startswith(f"{prefix}-"):
            return list(ADAPTIVE_SEQUENCE_STAGES)
    return None


def _adaptive_stage_blueprints() -> tuple[dict[str, Any], ...]:
    labels = {"recall": "Nhắc lại", "explain": "Giải thích", "why": "Lập luận", "transfer": "Chuyển giao"}
    return tuple(
        {
            "key": f"{bank['key']}-{stage}",
            "course_code": bank["course_code"],
            "week_start": "2026-10-19",
            "week_end": "2026-10-25",
            "assignment_title": bank["assignment_title"],
            "topic": f"{bank['topic']} · {labels[stage]}",
            "question": content["question"],
            "rubric": content["rubric"],
            "knowledge_component_ids": [bank["kc"]],
            "assessment_stage": stage,
            "source": bank["source"],
            "hints": content["hints"],
        }
        for bank in _ADAPTIVE_STAGE_BANKS
        for stage, content in bank["stages"].items()
    )


DEMO_ASSESSMENT_BLUEPRINTS += _adaptive_stage_blueprints()


def blueprint_payload(blueprint: dict[str, Any]) -> dict[str, Any]:
    """Return the versioned instructor-action shape without approving it."""

    stages = adaptive_stages_for_content_key(str(blueprint["key"])) or [blueprint["assessment_stage"]]
    return {
        "status": "review",
        "topic": blueprint["topic"],
        "question": blueprint["question"],
        "rubric": list(blueprint["rubric"]),
        "level": "application" if blueprint["assessment_stage"] == "application" else "conceptual",
        "source": blueprint["source"],
        "answerType": "open",
        "knowledgeComponentIds": list(blueprint["knowledge_component_ids"]),
        "kcProvisional": False,
        "assessmentStage": blueprint["assessment_stage"],
        "hints": list(blueprint["hints"]),
        "questionDesign": {
            "mode": "fixed",
            "relation_property": "transitive",
            "stages": stages,
            "reference_text": "",
        },
        "assignmentTitle": blueprint["assignment_title"],
        "weekStart": blueprint["week_start"],
        "weekEnd": blueprint["week_end"],
        "contentKey": blueprint["key"],
        "aiGenerated": True,
    }


def blueprints_for_window(start: date, end: date) -> list[dict[str, Any]]:
    """Select demo content whose teaching week overlaps the requested window."""

    return [
        item
        for item in DEMO_ASSESSMENT_BLUEPRINTS
        if date.fromisoformat(item["week_start"]) <= end and date.fromisoformat(item["week_end"]) >= start
    ]


def blueprint_by_topic(topic: str) -> dict[str, Any] | None:
    """Resolve a seeded quiz title to its teacher-reviewable content."""

    return next((item for item in DEMO_ASSESSMENT_BLUEPRINTS if item["topic"] == topic), None)
