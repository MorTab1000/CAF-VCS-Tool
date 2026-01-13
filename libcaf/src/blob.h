#ifndef BLOB_H
#define BLOB_H

#include <string>

class Blob {
public:
    const std::string hash;
    std::string data;

    Blob(const std::string& hash) : hash(hash) {}
    Blob(std::string&& hash) : hash(std::move(hash)) {}
    Blob(const std::string& hash, const std::string& data)  
        : hash(hash), data(data) {}
};

#endif //BLOB_H
