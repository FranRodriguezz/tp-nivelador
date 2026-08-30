package safe_socket

import "io"


// SendAll writes all bytes to socket, looping to handle short writes.
// Returns an error if the write fails or the connection is closed
// before all bytes could be sent.
func SendAll(socket io.Writer, bytes []byte) error {
	accumulated := 0
	bufferSize := len(bytes)
	for accumulated < bufferSize {
		n, err := socket.Write(bytes[accumulated:])
		if err != nil {
			return err
		}
		accumulated += n
	}
	return nil
}

// RecvAll reads all bytes from socket, looping to handle short reads.
// Returns an error if the read fails or the connection is closed
// before all bytes could be received.
func RecvAll(socket io.Reader, size int) ([]byte, error) {
	accumulated := 0
	buffer := make([]byte, size)
	for accumulated < size {
		n, err := socket.Read(buffer[accumulated:])
		if err != nil {
			return nil, err
		}
		accumulated += n
	}
	return buffer, nil
}
