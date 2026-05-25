# Dữ liệu

- Cào dữ liệu [Pháp Điển Việt Nam](https://phapdien.moj.gov.vn/Pages/home.aspx) để xây dựng cấu trúc bộ dữ liệu pháp luật.

- Cào dữ liệu [Văn bản quy phạm pháp luật](https://vbpl.vn/) để lấy dữ liệu.

## Dữ liệu Pháp Điển 

- Giải nén tệp zip tải xuống từ [Pháp Điển Việt Nam](https://phapdien.moj.gov.vn/Pages/home.aspx) vào data_crawler.
- Chạy file toJson.js để tạo 3 file json từ jsonData.js:
    - chude.json: các chủ đề.
    - demuc.json: các đề mục.
    - treeNode.json: các điều, chỉ mục, đề mục và chủ đề tương ứng.

```
node toJson.js
```

## Xây dựng cấu trúc luật

Chạy file structure_crawl.py

```
python structure_crawl.py
```

## Lấy dữ liệu các văn bản pháp luật

- Chạy file document_crawl.py

```
python document_crawl.py
```

- Chạy file build_unit.py

```
python build_unit.py
```