import aiofiles
import re
from utils.type_helpers import uint8, uint16, uint32, uint64, int32, int64

# Example
# 80010008 EA372703
# 00140000 00000000
# 180000E8 0000270F

QC_RE = re.compile(r"^([0-9a-fA-F]){8} ([0-9a-fA-F]){8}$")

class QuickCodesError(Exception):
    """Exception raised for errors relating to quick codes."""
    def __init__(self, message: str) -> None:
        self.message = message

class QuickCodes:
    """Functions to handle Save Wizard quick codes."""
    def __init__(self, filePath: str, codes: str) -> None:
        self.filePath = filePath
        self.codes = codes
        self.data = bytearray()

        parts = self.codes.split()
        try: 
            self.lines = [f"{parts[i]} {parts[i + 1]}" for i in range(0, len(parts), 2)]
        except IndexError: 
            raise QuickCodesError("Invalid code!")

        for line in self.lines:
            if not self.validate_code(line):
                raise QuickCodesError(f"Invalid code: {line}!")

    @staticmethod
    def search_data(data: bytearray | bytes, size: int, start: int, search: bytearray | bytes, length: int, count: int) -> int:
        k = 1
        s = search[:length]

        for i in range(start, size - length + 1):
            if data[i:i + length] == s:
                if k == count:
                    return i
                k += 1
        return -1

    @staticmethod
    def reverse_search_data(data: bytearray | bytes, size: int, start: int, search: bytearray | bytes, length: int, count: int) -> int:
        k = 1
        s = search[:length]
        
        for i in range(start, -1, -1):
            if (i + length <= size) and (data[i:i + length] == s) and (k == count):
                return i
            elif (i + length <= size) and (data[i:i + length] == s):
                k += 1
        return -1
    
    @staticmethod
    def validate_code(line: str) -> bool:
        return bool(QC_RE.fullmatch(line))

    async def read_file(self) -> None:
        async with aiofiles.open(self.filePath, "rb") as savegame:
            self.data.extend(await savegame.read())

    async def write_file(self) -> None:
        async with aiofiles.open(self.filePath, "wb") as savegame:
            await savegame.write(self.data)

    async def apply_code(self) -> None:
        pointer = int64()
        end_pointer = uint64()
        ptr = uint32()

        await self.read_file()

        line_index = 0
        while line_index < len(self.lines):
            line = self.lines[line_index]
        
            try:
                match line[0]:
                    case "0" | "1" | "2":
                        #	8-bit write
    			        #	0TXXXXXX 000000YY
                        #   16-bit write
    				    #   1TXXXXXX 0000YYYY
                        #   32-bit write
                        #   2TXXXXXX YYYYYYYY
                        #   X= Address/Offset
                        #   Y= Value to write
                        #   T=Address/Offset type (0 = Normal / 8 = Offset From Pointer)
                        bytes_ = uint8(1 << (ord(line[0]) - 0x30)).value

                        tmp6 = line[2:8]
                        off = int32(tmp6)
                        if line[1] == "8":
                            off.value += pointer.value
                        off = off.value

                        tmp8 = line[9:17]
                        val = uint32(tmp8, "little")

                        self.data[off:off + bytes_] = val.as_bytes[(4 - bytes_):(4 - bytes_) + bytes_]

                    case "3":
                        #	Increase / Decrease Write
                        #	Increases or Decreases a specified amount of data from a specific Address
                        #	This does not add/remove Bytes into the save, it just adjusts the value of the Bytes already in it
                        #	For the 8 Byte Value Type, it will write 4 Bytes of data but will continue to write the bytes afterwards if it cannot write any more.
                        #	3BYYYYYY XXXXXXXX
                        #	B = Byte Value & Offset Type
                        #	0 = Add 1 Byte  (000000XX)
                        #	1 = Add 2 Bytes (0000XXXX)
                        #	2 = Add 4 Bytes
                        #	3 = Add 8 Bytes
                        #	4 = Sub 1 Byte  (000000XX)
                        #	5 = Sub 2 Bytes (0000XXXX)
                        #	6 = Sub 4 Bytes
                        #	7 = Sub 8 Bytes
                        #	8 = Offset from Pointer; Add 1 Byte  (000000XX)
                        #	9 = Offset from Pointer; Add 2 Bytes (0000XXXX)
                        #	A = Offset from Pointer; Add 4 Bytes
                        #	B = Offset from Pointer; Add 8 Bytes
                        #	C = Offset from Pointer; Sub 1 Byte  (000000XX)
                        #	D = Offset from Pointer; Sub 2 Bytes (0000XXXX)
                        #	E = Offset from Pointer; Sub 4 Bytes
                        #	F = Offset from Pointer; Sub 8 Bytes
                        #	Y = Address
                        #	X = Bytes to Add/Sub
                        t = line[1]

                        tmp6 = line[2:8]
                        off = int32(tmp6)
                        if t in ["8", "9", "A", "C", "D", "E"]:
                            off.value += pointer.value
                        write = off.value
                        
                        tmp8 = line[9:17]
                        val = uint32(tmp8).value

                        match t:
                            case "0" | "8":
                                wv8 = self.data[write]
                                wv8 += (val & 0x000000FF)

                                self.data[write] = wv8
                            
                            case "1" | "9":
                                wv16 = uint16(self.data[write:write + 2], "little")
                                wv16.value += (val & 0x0000FFFF)
                                
                                self.data[write:write + 2] = wv16.as_bytes
                            
                            case "2" | "A":
                                wv32 = uint32(self.data[write:write + 4], "little")
                                wv32.value += val

                                self.data[write:write + 4] = wv32.as_bytes

                            case "3" | "B":
                                wv64 = uint64(self.data[write:write + 8], "little")
                                wv64.value += val

                                self.data[write:write + 8] = wv64.as_bytes

                            case "4" | "C":
                                wv8 = self.data[write]
                                wv8 -= (val & 0x000000FF)

                                self.data[write] = wv8

                            case "5" | "D":
                                wv16 = uint16(self.data[write:write + 2], "little")
                                wv16.value -= (val & 0x0000FFFF)

                                self.data[write:write + 2] = wv16.as_bytes
                            
                            case "6" | "E":
                                wv32 = uint32(self.data[write:write + 4], "little")
                                wv32.value -= val

                                self.data[write:write + 4] = wv32.as_bytes
                            
                            case "7" | "F":
                                wv64 = uint64(self.data[write:write + 8], "little")
                                wv64.value -= val

                                self.data[write:write + 8] = wv64.as_bytes
                            
                    case "4":
                        #	multi write
                        #	4TXXXXXX YYYYYYYY
                        #	4NNNWWWW VVVVVVVV | NNNNWWWW VVVVVVVV
                        #	X= Address/Offset
                        #	Y= Value to write (Starting)
                        #	N=Times to Write
                        #	W=Increase Address By
                        #	V=Increase Value By
                        #	T=Address/Offset type
                        #	Normal/Pointer
                        #	0 / 8 & 4 / C = 8bit
                        #	1 / 9 & 5 / D = 16bit
                        #	2 / A & 6 / E = 32bit
                        t = line[1]

                        tmp6 = line[2:8]
                        off = int32(tmp6)
                        if t in ["8", "9", "A", "C", "D", "E"]:
                            off.value += pointer.value
                        off = off.value
                        
                        tmp8 = line[9:17]
                        val = uint32(tmp8, "little")

                        line = self.lines[line_index + 1]
                        line_index += 1
                        
                        if t in ["4", "5", "6", "C", "D", "E"]:
                            # NNNNWWWW VVVVVVVV
                            tmp4 = line[:4]
                            n = int32(tmp4).value
                        else:
                            # 4NNNWWWW VVVVVVVV
                            tmp3 = line[1:4]
                            n = int32(tmp3).value

                        tmp4 = line[4:8]
                        incoff = int32(tmp4).value

                        tmp8 = line[9:17]
                        incval = uint32(tmp8).value

                        for i in range(n):
                            write = off + (incoff * i)

                            match t:
                                case "0" | "8" | "4" | "C":
                                    wv8 = uint8(val.value)

                                    self.data[write] = wv8.value
                                
                                case "1" | "9" | "5" | "D":
                                    wv16 = uint16(val.value, "little")

                                    self.data[write:write + 2] = wv16.as_bytes
                                
                                case "2" | "A" | "6" | "E":
                                    wv32 = val

                                    self.data[write:write + 4] = wv32.as_bytes
                            
                            val.value += incval

                    case "5":
                        #	copy bytes
                        #	5TXXXXXX ZZZZZZZZ
                        #	5TYYYYYY 00000000
                        #	  XXXXXX = Offset to copy from
                        #	  YYYYYY = Offset to copy to
                        #	         ZZZZZZZZ = Number of bytes to copy
                        #	 T = Bit Size
                        #	 0 = From start of the data
                        #	 8 = From found from a search
                        tmp6 = line[2:8]
                        off_src = int32(tmp6).value

                        tmp8 = line[9:17]
                        val = uint32(tmp8).value

                        src = off_src

                        if line[1] == "8":
                            src += pointer.value

                        line = self.lines[line_index + 1]
                        line_index += 1

                        tmp6 = line[2:8]
                        off_dst = int32(tmp6).value

                        dst = off_dst
                        
                        if line[1] == "8":
                            dst += pointer.value

                        self.data[dst:dst + val] = self.data[src:src + val]
                    
                    case "6":
                        #	special mega code
                        #	6TWX0Y0Z VVVVVVVV <- Code Type 6
                        #	6 = Type 6: Pointer codes
                        #	T = Data size of VVVVVVVV: 0:8bit, 1:16bit, 2:32bit, search-> 8:8bit, 9:16bit, A:32bit
                        #	W = operator:
                        #	      0X = Read "address" from file (X = 0:none, 1:add, 2:multiply)
                        #	      1X = Move pointer from obtained address ?? (X = 0:add, 1:substract, 2:multiply)
                        #	      2X = Move pointer ?? (X = 0:add, 1:substract, 2:multiply)
                        #	      4X = Write value: X=0 at read address, X=1 at pointer address
                        #	Y = flag relative to read add (very tricky to understand; 0=absolute, 1=pointer)
                        #	Z = flag relative to current pointer (very tricky to understand)
                        #	V = Data
                        t = line[1]
                        w = line[2]
                        x = line[3]
                        y = line[5]
                        z = line[7]

                        tmp8 = line[9:17]
                        val = uint32(tmp8, "little")

                        write = 0
                        off = 0

                        if t in ["8", "9", "A"]:
                            off += pointer.value

                        match w:
                            case "0":
                                # 0X = Read "address" from file (X = 0:none, 1:add, 2:multiply)
                                if x == "1":
                                    val.value += ptr.value
                                write += (val.value + off)
                            
                                if y == "1":
                                    pointer.value = val.value
                                
                                match t:
                                    case "0" | "8":
                                        # Data size = 8 bits
						                # 000000VV
                                        wv8 = self.data[write]
                                        ptr.value = wv8

                                    case "1" | "9":
                                        # Data size = 16 bits
						                # 0000VVVV
                                        wv16 = uint16(self.data[write:write + 2], "little")
                                        ptr.value = wv16.value
                                    
                                    case "2" | "A":
                                        # Data size = 32 bits
						                # VVVVVVVV
                                        wv32 = uint32(self.data[write:write + 4], "little")
                                        ptr.value = wv32.value

                            case "1":
                                # 1X = Move pointer from obtained address ?? (X = 0:add, 1:substract, 2:multiply)
                                match x:
                                    case "0":
                                        ptr.value += val.value
                                    
                                    case "1":
                                        ptr.value -= val.value
                                    
                                    case "2":
                                        ptr.value *= val.value
                                
                                if z == "1":
                                    ptr.value += pointer.value
                                pointer.value = ptr.value
                            
                            case "2":
                                # 2X = Move pointer ?? (X = 0:add, 1:substract, 2:multiply)
                                match x:
                                    case "0":
                                        pointer.value += val.value
                                    
                                    case "1":
                                        pointer.value -= val.value
                                    
                                    case "2":
                                        pointer.value *= val.value
                                    
                                if y == "1":
                                    ptr.value = pointer.value
                            
                            case "4":
                                # 4X = Write value: X=0 at read address, X=1 at pointer address
                                write += pointer.value

                                match t:
                                    case "0" | "8":
                                        wv8 = uint8(val.value)
                        
                                        self.data[write] = wv8
                                    
                                    case "1" | "9":
                                        wv16 = uint16(val, "little")

                                        self.data[write:write + 2] = wv16.as_bytes

                                    case "2" | "A":
                                        wv32 = val

                                        self.data[write:write + 4] = wv32.as_bytes
                    
                    case "7":
                        #	Writes Bytes up to a specified Maximum/Minimum to a specific Address
                        #	This code is the same as a standard write code however it will only write the bytes if the current value at the address is no more or no less than X.
                        #	For example, you can use a no less than value to make sure the address has more than X but will take no effect if it already has more than the value on the save.
                        #	7BYYYYYY XXXXXXXX
                        #	B = Byte Value & Offset Type
                        #	0 = No Less Than: 1 Byte  (000000XX)
                        #	1 = No Less Than: 2 Bytes (0000XXXX)
                        #	2 = No Less Than: 4 Bytes
                        #	4 = No More Than: 1 Byte  (000000XX)
                        #	5 = No More Than: 2 Bytes (0000XXXX)
                        #	6 = No More Than: 4 Bytes
                        #	8 = Offset from Pointer; No Less Than: 1 Byte  (000000XX)
                        #	9 = Offset from Pointer; No Less Than: 2 Bytes (0000XXXX)
                        #	A = Offset from Pointer; No Less Than: 4 Bytes
                        #	C = Offset from Pointer; No More Than: 1 Byte  (000000XX)
                        #	D = Offset from Pointer; No More Than: 2 Bytes (0000XXXX)
                        #	E = Offset from Pointer; No More Than: 4 Bytes
                        #	Y = Address
                        #	X = Bytes to Write
                        t = line[1]

                        tmp6 = line[2:8]
                        off = int32(tmp6)

                        if t in ["8", "9", "A", "C", "D", "E"]:
                            off.value += pointer.value
                        write = off.value

                        tmp8 = line[9:17]
                        val = uint32(tmp8).value

                        match t:
                            case "0" | "8":
                                val &= 0x000000FF
                                wv8 = self.data[write]
                                if val > wv8: 
                                    wv8 = val

                                self.data[write] = wv8

                            case "1" | "9":
                                val &= 0x0000FFFF
                                wv16 = uint16(self.data[write:write + 2], "little")
                                if val > wv16.value: 
                                    wv16.value = val

                                self.data[write:write + 2] = wv16.as_bytes
                            
                            case "2" | "A":
                                wv32 = uint32(self.data[write:write + 4], "little")
                                if val > wv32.value: 
                                    wv32.value = val

                                self.data[write:write + 4] = wv32.as_bytes
                            
                            case "4" | "C":
                                val &= 0x000000FF
                                wv8 = self.data[write]
                                if val < wv8: 
                                    wv8 = val

                                self.data[write] = wv8

                            case "5" | "D":
                                val &= 0x0000FFFF
                                wv16 = uint16(self.data[write:write + 2], "little")
                                if val < wv16.value: 
                                    wv16.value = val

                                self.data[write:write + 2] = wv16.as_bytes

                            case "6" | "E":
                                wv32 = uint32(self.data[write:write + 4], "little")
                                if val < wv32.value: 
                                    wv32.value = val

                                self.data[write:write + 4] = wv32.as_bytes

                    case "8":
                        #	Search Type
                        #	8TZZXXXX YYYYYYYY
                        #	T= Address/Offset type (0 = Normal / 8 = Offset From Pointer)
                        #	Z= Amount of times to find before Write
                        #	X= Amount of data to Match
                        #	Y= Seach For (note can be extended for more just continue it like YYYYYYYY YYYYYYYY under it)
                        #	Once u have your Search type done then place one of the standard code types under it with setting T to the Pointer type
                        t = line[1]

                        tmp3 = line[2:4]
                        cnt = int32(tmp3).value

                        tmp4 = line[4:8]
                        length = int32(tmp4).value

                        tmp8 = line[9:17]
                        val = uint32(tmp8, "big")

                        find = bytearray((length + 3) & ~3)

                        if not cnt: 
                            cnt = 1

                        find[:4] = val.as_bytes

                        for i in range(4, length, 8):
                            line = self.lines[line_index + 1]
                            line_index += 1

                            tmp8 = line[:8]
                            val.value = tmp8

                            find[i:i + 4] = val.as_bytes

                            tmp8 = line[9:17]
                            val.value = tmp8

                            if i + 4 < length:
                                find[(i + 4):(i + 4) + 4] = val.as_bytes

                        pointer.value = self.search_data(self.data, len(self.data), pointer.value if t == "8" else 0, find, length, cnt)

                        if pointer.value < 0:
                            while line_index < len(self.lines):
                                line_index += 1

                                while (line and ((line[0] not in ["8", "B", "C"]) or line[1] == "8")):
                                    if line_index >= len(self.lines):
                                        break
                                    
                                    line = self.lines[line_index]
                                    line_index += 1
                            pointer.value = 0

                    case "9":
                        #	Pointer Manipulator (Set/Move Pointer)
                        #	Adjusts the Pointer Offset using numerous Operators
                        #	9Y000000 XXXXXXXX
                        #	Y = Operator
                        #	0 = Set Pointer to Big Endian value at XXXXXXXX
                        #	1 = Set Pointer to Little Endian value at XXXXXXXX
                        #	2 = Add X to Pointer
                        #	3 = Sub X to Pointer
                        #	4 = Set Pointer to the end of file and subtract X
                        #	5 = Set Pointer to X
                        #	D = Set End Address = to X
                        #	E = Set End Address From Pointer + X
                        #	X = Value to set / change
                        #	---
                        #	Move pointer to offset in address XXXXXXXXX (CONFIRMED CODE)
                        #	90000000 XXXXXXXX
                        #	---
                        #	Step Forward Code (CONFIRMED CODE)
                        #	92000000 XXXXXXXX
                        #	---
                        #	Step Back Code (CONFIRMED CODE)
                        #	93000000 XXXXXXXX
                        #	---
                        #	Step Back From End of File Code (CONFIRMED CODE)
                        #	94000000 XXXXXXXX
                        tmp8 = line[9:17]
                        off = uint32(tmp8).value

                        match line[1]:
                            case "0":
                                val = uint32(self.data[off:off + 4], "big")
                                pointer.value = val.value
                            
                            case "1":
                                val = uint32(self.data[off:off + 4], "little")
                                pointer.value = val.value
                            
                            case "2":
                                pointer.value += off
                            
                            case "3":
                                pointer.value -= off
                            
                            case "4": 
                                pointer.value = len(self.data) - off
                            
                            case "5":
                                pointer.value = off

                            case "D":
                                end_pointer.value = off

                            case "E":
                                end_pointer.value = pointer.value + off

                    case "A":
                        #	Multi-write
                        #	ATxxxxxx yyyyyyyy  (xxxxxx = address, yyyyyyyy = size)
                        #	zzzzzzzz zzzzzzzz  <-data to write at address
                        #	T= Address/Offset type (0 = Normal / 8 = Offset From Pointer)
                        t = line[1]

                        tmp6 = line[2:8]
                        off = int32(tmp6)
                        if t == "8":
                            off.value += pointer.value
                        off = off.value

                        tmp8 = line[9:17]
                        size = uint32(tmp8).value

                        write = bytearray((size + 3) & ~3)

                        for i in range(0, size, 8):
                            line = self.lines[line_index + 1]
                            line_index += 1

                            tmp8 = line[:8]
                            val = uint32(tmp8, "big")

                            write[i:i + 4] = val.as_bytes

                            tmp8 = line[9:17]
                            val.value = tmp8

                            if (i + 4) < size:
                                write[(i + 4):(i + 4) + 4] = val.as_bytes
                        
                        self.data[off:off + size] = write[:size] 

                    case "B":
                        #	Backward Byte Search (Set Pointer)
                        #	Searches Backwards for a specified Value and saves the Value's Address as the Pointer Offset
                        #	Will start from the end of the save file, but can be changed using a previous Pointer Offset
                        #	BTCCYYYY XXXXXXXX
                        #	*Other Code Here, Use Specific Offset Type*
                        #	T = Offset Type
                        #	0 = Default
                        #	8 = Offset from Pointer
                        #	C = Amount of Times to Find until Pointer Set
                        #	Y = Amount of Bytes to Search
                        #	1 = 1 Byte
                        #	2 = 2 Bytes
                        #	and so on...
                        #	X = Bytes to Search, use Multiple Lines if Needed
                        t = line[1]

                        tmp3 = line[2:4] 
                        cnt = int32(tmp3).value

                        tmp4 = line[4:8]
                        length = int32(tmp4).value

                        tmp8 = line[9:17]
                        val = uint32(tmp8, "big")

                        find = bytearray((length + 3) & ~3)
                        if not cnt: 
                            cnt = 1
                        if not end_pointer.value: 
                            end_pointer.value = len(self.data) - 1

                        find[:4] = val.as_bytes

                        for i in range(4, length, 8):
                            line = self.lines[line_index + 1]
                            line_index += 1

                            tmp8 = line[:8]
                            val.value = tmp8

                            find[i:i + 4] = val.as_bytes

                            tmp8 = line[9:17]
                            val.value = tmp8

                            if (i + 4) < length:
                                find[(i + 4):(i + 4) + 4] = val.as_bytes

                        pointer.value = self.reverse_search_data(self.data, len(self.data), pointer.value if t == "8" else end_pointer.value, find, length, cnt)
                        
                        if pointer.value < 0:
                            while line_index < len(self.lines):
                                line_index += 1

                                while (line and ((line[0] not in ["8", "B", "C"]) or line[1] == "8")):
                                    if line_index >= len(self.lines):
                                        break
                                    
                                    line = self.lines[line_index]
                                    line_index += 1
                            pointer.value = 0
                    
                    case "C":
                        #	Address Byte Search (Set Pointer)
                        #	Searches for a Value from a specified Address and saves the new Value's Address as the Pointer Offset
                        #	Rather than searching for Bytes already given such as code types 8 and B, this code will instead search using the bytes at a specific Address
                        #	CBFFYYYY XXXXXXXX
                        #	*Other Code Here, Use Specific Offset Type*
                        #	B = Offset Type
                        #	0 = Search Forwards from Address Given
                        #	4 = Search from 0x0 to Address Given
                        #	8 = Offset from Pointer; Search Forwards from Address Given
                        #	C = Offset from Pointer; Search from 0x0 to Address Given
                        #	F = Amount of Times to Find until Pointer Set
                        #	Y = Amount of Bytes to Search from Address
                        #	1 = 1 Byte
                        #	2 = 2 Bytes
                        #	and so on...
                        #	X = Address of Bytes to Search with
                        t = line[1]

                        tmp3 = line[2:4]
                        cnt = int32(tmp3).value

                        tmp4 = line[4:8]
                        length = int32(tmp4).value

                        tmp8 = line[9:17]
                        addr = uint32(tmp8)
                        if t in ["8", "C"]:
                            addr.value += pointer.value
                        addr = addr.value

                        find = self.data[addr:]

                        if not cnt: 
                            cnt = 1

                        if t in ["4", "C"]:
                            pointer.value = self.search_data(self.data, addr + length, 0, find, length, cnt)
                        else:
                            pointer.value = self.search_data(self.data, len(self.data), addr + length, find, length, cnt)

                        if pointer.value < 0:
                            while line_index < len(self.lines):
                                line_index += 1

                                while (line and ((line[0] not in ["8", "B", "C"]) or line[1] == "8")):
                                    if line_index >= len(self.lines):
                                        break
                                    
                                    line = self.lines[line_index]
                                    line_index += 1
                            pointer.value = 0

                    case "D":
                        #	2 Byte Test Commands (Code Skipper)
                        #	Test a specific Address using an Operation; skips the following code lines if Operation fails
                        #	DBYYYYYY CCZDXXXX
                        #	B = Offset Type
                        #	0 = Normal
                        #	8 = Offset from Pointer
                        #	Y = Address to test
                        #	C = Lines of code to skip if test fails
                        #	Z = Value data type
                        #	0 = 16-bit
                        #	1 = 8-bit
                        #	D = Test Operation
                        #	0 = Equal
                        #	1 = Not Equal
                        #	2 = Greater Than (Value at the Address is greater than the tested value)
                        #	3 = Less Than (Value at the Address is less than the tested value)
				        #	X = Value to test
                        t = line[1]
                        op = line[12]
                        bit = line[11]

                        tmp6 = line[2:8]
                        off = int32(tmp6)
                        if t == "8":
                            off.value += pointer.value
                        off = off.value

                        tmp3 = line[9:11]
                        l = int32(tmp3)

                        tmp4 = line[13:17]
                        val = int32(tmp4).value

                        src = uint16(self.data[off:off + 2], "little").value

                        if bit == "1":
                            val &= 0xFF
                            src = self.data[off]
                        
                        match op:
                            case "0":
                                off = (src == val)

                            case "1":
                                off = (src != val)

                            case "2":
                                off = (src > val)
                            
                            case "3":
                                off = (src < val)

                            case _:
                                off = 1
                        
                        if not off:
                            while l.value > 0:
                                l.value -= 1
                                line = self.lines[line_index + 1]
                                line_index += 1
            # except NotImplementedError:
            #     raise QuickCodesError("A code-type you entered has not yet been implemented!")
            except (ValueError, IOError, IndexError):
                raise QuickCodesError("Invalid code!")

            line_index += 1
        
        await self.write_file()
