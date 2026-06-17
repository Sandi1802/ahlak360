-- ═══════════════════════════════════════════════════════════════
--  AKHLAK 360° - MySQL Database Schema
-- ═══════════════════════════════════════════════════════════════
CREATE DATABASE IF NOT EXISTS akhlak360_db;
USE akhlak360_db;

-- 1. Table: karyawan
CREATE TABLE IF NOT EXISTS karyawan (
    id_karyawan INT AUTO_INCREMENT PRIMARY KEY,
    nip VARCHAR(50) UNIQUE NOT NULL,
    nama VARCHAR(150) NOT NULL,
    jabatan VARCHAR(100) NOT NULL,
    departemen VARCHAR(100) NOT NULL,
    id_atasan INT NULL,
    FOREIGN KEY (id_atasan) REFERENCES karyawan(id_karyawan) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. Table: user
CREATE TABLE IF NOT EXISTS user (
    id_user INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL,
    id_karyawan INT NULL,
    FOREIGN KEY (id_karyawan) REFERENCES karyawan(id_karyawan) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. Table: kuesioner
CREATE TABLE IF NOT EXISTS kuesioner (
    id_kuesioner INT AUTO_INCREMENT PRIMARY KEY,
    nama_kuesioner VARCHAR(255) NOT NULL,
    periode VARCHAR(50) NOT NULL,
    tanggal_mulai DATE,
    tanggal_selesai DATE,
    status VARCHAR(20) DEFAULT 'draft'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. Table: pertanyaan
CREATE TABLE IF NOT EXISTS pertanyaan (
    id_pertanyaan INT AUTO_INCREMENT PRIMARY KEY,
    id_kuesioner INT NOT NULL,
    dimensi_akhlak VARCHAR(100) NOT NULL,
    urutan INT NOT NULL,
    teks_pertanyaan TEXT NOT NULL,
    FOREIGN KEY (id_kuesioner) REFERENCES kuesioner(id_kuesioner) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. Table: penilai
CREATE TABLE IF NOT EXISTS penilai (
    id_penilai INT AUTO_INCREMENT PRIMARY KEY,
    id_kuesioner INT NOT NULL,
    id_karyawan_dinilai INT NOT NULL,
    id_karyawan_penilai INT NOT NULL,
    kategori VARCHAR(50) NOT NULL,
    status_pengisian VARCHAR(20) DEFAULT 'belum',
    tanggal_pengisian DATETIME NULL,
    FOREIGN KEY (id_kuesioner) REFERENCES kuesioner(id_kuesioner) ON DELETE CASCADE,
    FOREIGN KEY (id_karyawan_dinilai) REFERENCES karyawan(id_karyawan) ON DELETE CASCADE,
    FOREIGN KEY (id_karyawan_penilai) REFERENCES karyawan(id_karyawan) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6. Table: jawaban
CREATE TABLE IF NOT EXISTS jawaban (
    id_jawaban INT AUTO_INCREMENT PRIMARY KEY,
    id_penilai INT NOT NULL,
    id_pertanyaan INT NOT NULL,
    skor INT NOT NULL,
    is_draft INT DEFAULT 1,
    FOREIGN KEY (id_penilai) REFERENCES penilai(id_penilai) ON DELETE CASCADE,
    FOREIGN KEY (id_pertanyaan) REFERENCES pertanyaan(id_pertanyaan) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 7. Table: hasil_penilaian
CREATE TABLE IF NOT EXISTS hasil_penilaian (
    id_hasil INT AUTO_INCREMENT PRIMARY KEY,
    id_kuesioner INT NOT NULL,
    id_karyawan INT NOT NULL,
    dimensi VARCHAR(50) NOT NULL,
    skor_atasan FLOAT DEFAULT 0,
    skor_rekan FLOAT DEFAULT 0,
    skor_bawahan FLOAT DEFAULT 0,
    skor_diri FLOAT DEFAULT 0,
    skor_akhir FLOAT DEFAULT 0,
    FOREIGN KEY (id_kuesioner) REFERENCES kuesioner(id_kuesioner) ON DELETE CASCADE,
    FOREIGN KEY (id_karyawan) REFERENCES karyawan(id_karyawan) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ═══════════════════════════════════════════════════════════════
-- Seed Data Awal
-- ═══════════════════════════════════════════════════════════════

-- Insert Admin HC
INSERT INTO user (username, password_hash, role, id_karyawan) 
VALUES ('admin', MD5('admin'), 'hc', NULL)
ON DUPLICATE KEY UPDATE id_user=id_user;
