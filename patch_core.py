"""Build the mapinfo12pro native test core for MapInfo 12.0.2 Build 208."""

import argparse
from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct

from keystone import KS_ARCH_X86, KS_MODE_32, Ks
from native_history import build_history


SUPPORTED_CORE = "5c0633da51941635bf897c7409ff976afdb685e9a5c92658795ee073a4dbde64"

WOR_PATH_CALL = 0x1B19FB
ORIGINAL_WOR_PATH = 0x40ED60
OPEN_APPEND = 0x40EF70
OPEN_APPEND_CONTINUE = 0x40EF77
OPEN_FAILURE = 0x40EF92
APPEND_BYTES = bytes.fromhex("8B C8 C1 E9 02 F3 A5")
TEXT_FLAGS = 0x60000020  # execute + read, initialized code
HISTORY_SLOT = 0x68AF5C


def align(number, boundary):
    return (number + boundary - 1) & -boundary


def jump(opcode, origin, target):
    return bytes([opcode]) + struct.pack("<I", (target - origin - 5) & 0xFFFFFFFF)


@dataclass(frozen=True)
class Section:
    rva: int
    virtual_size: int
    file_offset: int
    file_size: int


class CoreImage:
    def __init__(self, source):
        self.data = bytearray(source)
        self.pe, = struct.unpack_from("<I", source, 0x3C)
        if source[:2] != b"MZ" or source[self.pe:self.pe + 4] != b"PE\0\0":
            raise ValueError("Expected a Windows PE DLL.")
        self.coff = self.pe + 4
        self.optional = self.coff + 20
        machine, self.section_count = struct.unpack_from("<HH", source, self.coff)
        optional_size, = struct.unpack_from("<H", source, self.coff + 16)
        magic, = struct.unpack_from("<H", source, self.optional)
        if machine != 0x14C or magic != 0x10B:
            raise ValueError("Expected the 32-bit MapInfo core.")
        self.section_alignment, self.file_alignment = struct.unpack_from("<II", source, self.optional + 32)
        self.section_table = self.optional + optional_size
        self.sections = []
        for index in range(self.section_count):
            offset = self.section_table + 40 * index
            virtual_size, rva, file_size, file_offset = struct.unpack_from("<IIII", source, offset + 8)
            self.sections.append(Section(rva, virtual_size, file_offset, file_size))

    def file_offset(self, rva):
        for section in self.sections:
            delta = rva - section.rva
            if 0 <= delta < section.file_size:
                return section.file_offset + delta
        raise ValueError(f"RVA {rva:#x} is outside the file-backed sections.")

    def replace(self, rva, expected, updated):
        offset = self.file_offset(rva)
        end = offset + len(expected)
        if len(expected) != len(updated) or self.data[offset:end] != expected:
            raise ValueError(f"Instruction check failed at RVA {rva:#x}.")
        self.data[offset:end] = updated

    @property
    def new_section_rva(self):
        end = max(section.rva + max(section.virtual_size, section.file_size) for section in self.sections)
        return align(end, self.section_alignment)

    def append_code(self, payload):
        entry = self.section_table + 40 * self.section_count
        first_raw = min(section.file_offset for section in self.sections if section.file_size)
        if entry + 40 > first_raw or any(self.data[entry:entry + 40]):
            raise ValueError("The PE does not have room for a new section header.")
        rva = self.new_section_rva
        raw = align(len(self.data), self.file_alignment)
        raw_size = align(len(payload), self.file_alignment)
        header = struct.pack("<8sIIIIIIHHI", b".mi12pro", len(payload), rva,
                             raw_size, raw, 0, 0, 0, 0, TEXT_FLAGS)
        self.data[entry:entry + 40] = header
        struct.pack_into("<H", self.data, self.coff + 2, self.section_count + 1)
        old_code, = struct.unpack_from("<I", self.data, self.optional + 4)
        struct.pack_into("<I", self.data, self.optional + 4, old_code + raw_size)
        struct.pack_into("<I", self.data, self.optional + 56, align(rva + len(payload), self.section_alignment))
        struct.pack_into("<I", self.data, self.optional + 64, 0)  # optional PE checksum
        self.data.extend(bytes(raw - len(self.data)))
        self.data.extend(payload)
        self.data.extend(bytes(raw_size - len(payload)))

    def reserve_history_slot(self):
        for index, section in enumerate(self.sections):
            if section.rva + section.virtual_size != HISTORY_SLOT:
                continue
            offset = self.section_table + 40 * index
            flags, = struct.unpack_from("<I", self.data, offset + 36)
            if (self.data[offset:offset + 8].rstrip(b"\0") != b".data" or
                    not flags & 0x80000000 or section.file_size >= section.virtual_size or
                    HISTORY_SLOT % 4 or
                    align(HISTORY_SLOT + 4, self.section_alignment) != align(HISTORY_SLOT, self.section_alignment)):
                break
            struct.pack_into("<I", self.data, offset + 8, section.virtual_size + 4)
            return
        raise ValueError("The PE does not have a safe zero-initialized history pointer slot.")


def assemble(source, rva):
    engine = Ks(KS_ARCH_X86, KS_MODE_32)
    encoding, _ = engine.asm(source, addr=rva, as_bytes=True)
    if not encoding:
        raise ValueError("Assembly produced no bytes.")
    return encoding


def relative_path_code(rva, strings_rva, procedure_rva):
    # This call site passes a table path identifier, output buffer and WOR path identifier.
    # GetModuleHandleA and GetProcAddress are IAT entries of the checked build.
    return assemble(f"""
        push ebp
        mov ebp, esp
        push ebx
        push esi
        push edi
        call load_base
    load_base:
        pop ebx
        sub ebx, {rva + 11:#x}
        sub esp, 0x520
        mov esi, dword ptr [ebp + 12]
        push dword ptr [ebp + 16]
        push esi
        push dword ptr [ebp + 8]
        call {ORIGINAL_WOR_PATH:#x}
        add esp, 12
        mov dword ptr [ebp - 0x10], eax
        cmp byte ptr [esi + 1], 0x3a
        jne done
        cmp byte ptr [esi + 2], 0x5c
        jne done
        cmp dword ptr [ebp + 16], 0
        je done
        lea edi, [ebp - 0x520]
        push edi
        push dword ptr [ebp + 16]
        call 0x40ee90
        add esp, 8
        cmp byte ptr [edi + 1], 0x3a
        jne done
        cmp byte ptr [edi + 2], 0x5c
        jne done
        xor ecx, ecx
    check_length:
        cmp ecx, 0x104
        jae done
        cmp byte ptr [edi + ecx], 0
        je resolve_api
        inc ecx
        jmp check_length
    resolve_api:
        lea eax, [ebx + {strings_rva:#x}]
        push eax
        call dword ptr [ebx + 0x5352bc]
        test eax, eax
        je done
        lea edx, [ebx + {procedure_rva:#x}]
        push edx
        push eax
        call dword ptr [ebx + 0x535274]
        test eax, eax
        je done
        push 0x80
        push esi
        push 0x80
        push edi
        lea edi, [ebp - 0x118]
        push edi
        call eax
        test eax, eax
        je done
        xor ecx, ecx
    copy_relative:
        mov al, byte ptr [edi + ecx]
        mov byte ptr [esi + ecx], al
        inc ecx
        test al, al
        jne copy_relative
    done:
        mov eax, dword ptr [ebp - 0x10]
        lea esp, [ebp - 12]
        pop edi
        pop esi
        pop ebx
        pop ebp
        ret
    """, rva)


def open_guard_code(rva):
    # EDI points at the end of the directory in a 260-byte local buffer.
    # EAX includes the trailing NUL of the filename being appended.
    return assemble(f"""
        lea edx, [esp + 0x114]
        mov ecx, edi
        sub ecx, edx
        add ecx, eax
        cmp ecx, 0x104
        ja too_long
        mov ecx, eax
        shr ecx, 2
        rep movsd dword ptr es:[edi], dword ptr [esi]
        jmp {OPEN_APPEND_CONTINUE:#x}
    too_long:
        mov eax, -1
        xor ecx, ecx
        jmp {OPEN_FAILURE:#x}
    """, rva)


def preview_payload(section, history_slot=HISTORY_SLOT):
    module = b"shlwapi.dll\0"
    strings = module + b"PathRelativePathToA\0"
    relative_rva = section + 0x40
    relative = relative_path_code(relative_rva, section, section + len(module))
    guard_rva = relative_rva + len(relative)
    guard = open_guard_code(guard_rva)
    payload = strings.ljust(0x40, b"\0") + relative + guard
    history_code, history_hooks = build_history(section + len(payload), history_slot, assemble)
    changes = (
        (WOR_PATH_CALL, jump(0xE8, WOR_PATH_CALL, ORIGINAL_WOR_PATH), jump(0xE8, WOR_PATH_CALL, relative_rva)),
        (OPEN_APPEND, APPEND_BYTES, jump(0xE9, OPEN_APPEND, guard_rva) + b"\x90\x90"),
    )
    history_changes = tuple(
        (site, jump(0xE8, site, original), jump(0xE8, site, replacement))
        for site, original, replacement in history_hooks
    )
    return payload + history_code, changes + history_changes


def patch(source):
    digest = hashlib.sha256(source).hexdigest()
    if digest != SUPPORTED_CORE:
        raise ValueError(f"Unsupported micore.dll (SHA-256 {digest}).")
    image = CoreImage(source)
    image.reserve_history_slot()
    payload, changes = preview_payload(image.new_section_rva)
    for rva, expected, replacement in changes:
        image.replace(rva, expected, replacement)
    image.append_code(payload)
    return bytes(image.data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="path to a supported MapInfo micore.dll")
    parser.add_argument("output", type=Path, help="a new DLL path in an isolated test copy")
    arguments = parser.parse_args()
    try:
        result = patch(arguments.source.read_bytes())
        with arguments.output.open("xb") as output:
            output.write(result)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(f"{arguments.output}  SHA-256 {hashlib.sha256(result).hexdigest()}")


if __name__ == "__main__":
    main()
